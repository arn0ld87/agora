/**
 * StepSimulationFeedView — Vitest-Smoke-Tests.
 *
 * Slice FE-Redesign-5 · 2026-05-15
 * Slice UI-2b (#1713), Commit 3: View umgebaut auf FeedTimeline/SimFilterBar/
 * SimRunHeader (docs/design/simulation-feed.md §2.5) — Stubs und Assertions
 * auf die alte Dual-Column-Struktur (FeedColumn/SimulationPulseBar/
 * RedditThread/TwitterPost) sind entfallen, die View importiert sie nicht
 * mehr direkt.
 *
 * Prueft:
 * 1. Mock-Stream injiziert Posts → useSimFeed empfängt sie.
 * 2. Snapshot wird für beide Plattformen geladen, Stream startet zuerst.
 * 3. Reddit- und Twitter-Posts landen als FeedItem in der Timeline.
 * 4. openThread navigiert per router.push zu SimThreadFocus.
 * 5. Unmount/Remount: Store-Bestand bleibt erhalten (Slice 9 · #1007).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed } from 'vue'
import { resetSimFeedStore } from '@/composables/useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

// ---- Mocks ----

let capturedPostCreatedHandler: ((data: PostCreatedEvent) => void) | undefined
let snapshotFetchCalls: { simulationId: string; platform: string }[] = []
let snapshotFeed: PostCreatedEvent[] = []

// Reihenfolge-Tracker: Race-Condition-Regression (#1009 Codex-Finding).
let callOrder = 0
let streamStartOrder = -1
let snapshotFirstFetchOrder = -1

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshot: (simulationId: string, platform: string) => {
    if (snapshotFirstFetchOrder === -1) snapshotFirstFetchOrder = callOrder++
    snapshotFetchCalls.push({ simulationId, platform })
    return Promise.resolve(snapshotFeed.filter((p) => p.platform === platform))
  },
  getSimulationRounds: () => Promise.resolve({ success: true, data: { rounds: [] } }),
}))

vi.mock('@/api/envelope', () => ({
  unwrap: (envelope: { data: unknown }) => envelope.data,
}))

vi.mock('@/composables/useEventStream', () => ({
  useEventStream: (_id: string, handlers: { post_created?: (data: PostCreatedEvent) => void }) => {
    capturedPostCreatedHandler = handlers?.post_created
    return {
      isStreaming: { value: true },
      error: { value: null },
      lastEventAt: { value: null },
      lastTraceId: { value: null },
      start: vi.fn(() => {
        streamStartOrder = callOrder++
        return Promise.resolve()
      }),
      stop: vi.fn(),
    }
  },
}))

// @tanstack/vue-virtual misst reale Layout-Groessen (ResizeObserver,
// clientHeight) — jsdom liefert dafuer keine sinnvollen Werte, siehe
// FeedTimeline.spec.ts.
vi.mock('@tanstack/vue-virtual', () => ({
  useVirtualizer: (optionsRef: { value: { count: number } }) =>
    computed(() => {
      const count = optionsRef.value.count
      const rows = Array.from({ length: count }, (_, index) => ({ index, start: index * 120 }))
      return {
        getVirtualItems: () => rows,
        getTotalSize: () => count * 120,
        scrollToIndex: () => {},
      }
    }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

// useRoute/useRouter mocken — die View navigiert seit Slice UI-2b (#1713)
// per router.push() zu SimThreadFocus (openThread), statt nur die Route zu
// lesen.
const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()
let currentQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { simulationId: 'test-sim-1' }, query: currentQuery }),
  useRouter: () => ({ push: routerPushMock, replace: routerReplaceMock }),
}))

// useSimFeed batcht eingehende Posts pro Animation Frame (#1007). jsdoms
// requestAnimationFrame loest erst nach ~16ms Realzeit aus; rAF-Stub macht
// den Flush synchron.
vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  cb(0)
  return 0
})

import StepSimulationFeedView from '../StepSimulationFeedView.vue'

function mountFeed() {
  return mount(StepSimulationFeedView)
}

// ---- Helpers ----
function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'test-sim-1',
    post_id: `p-${Math.random().toString(36).slice(2)}`,
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    persona_name: 'Test Persona',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'Test',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

describe('StepSimulationFeedView', () => {
  beforeEach(() => {
    resetSimFeedStore('test-sim-1')
    capturedPostCreatedHandler = undefined
    snapshotFetchCalls = []
    snapshotFeed = []
    callOrder = 0
    streamStartOrder = -1
    snapshotFirstFetchOrder = -1
    currentQuery = {}
    routerPushMock.mockClear()
  })

  it('mountet ohne Crash und stellt Stream auf', async () => {
    const wrapper = mountFeed()
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
  })

  it('#1009: holt Feed-Snapshot für reddit und twitter beim Mount', async () => {
    mountFeed()
    await flushPromises()
    const platforms = snapshotFetchCalls.map((c) => c.platform).sort()
    expect(platforms).toEqual(['reddit', 'twitter'])
    expect(snapshotFetchCalls.every((c) => c.simulationId === 'test-sim-1')).toBe(true)
  })

  it('#1009: startet den Stream VOR dem Snapshot-Fetch (Race-Condition, Codex-Finding)', async () => {
    mountFeed()
    await flushPromises()
    expect(streamStartOrder).toBeGreaterThanOrEqual(0)
    expect(snapshotFirstFetchOrder).toBeGreaterThanOrEqual(0)
    expect(streamStartOrder).toBeLessThan(snapshotFirstFetchOrder)
  })

  it('#1009: Snapshot-Posts werden beim Mount in den Feed ingestiert und als FeedItem gerendert', async () => {
    snapshotFeed = [
      mkPost({ platform: 'reddit', post_id: 'snap-r-1' }),
      mkPost({ platform: 'twitter', post_id: 'snap-t-1' }),
    ]

    const wrapper = mountFeed()
    await flushPromises()

    expect(wrapper.findAll('.fi-root')).toHaveLength(2)
  })

  it('Reddit- und Twitter-Posts aus dem Stream landen in der Timeline', async () => {
    const wrapper = mountFeed()
    await flushPromises()

    for (let i = 0; i < 5; i++) {
      capturedPostCreatedHandler?.(mkPost({ platform: 'reddit', post_id: `r-${i}` }))
    }
    for (let i = 0; i < 3; i++) {
      capturedPostCreatedHandler?.(mkPost({ platform: 'twitter', post_id: `t-${i}` }))
    }
    await flushPromises()

    expect(wrapper.findAll('.fi-root')).toHaveLength(8)
  })

  // Regression: 'connecting' (Erstverbindung) wurde vor dem Fix auf
  // 'reconnecting' gemappt und zeigte faelschlich den "Verbindung
  // verloren"-Banner beim allerersten Laden (FeedTimeline.vue).
  it('Erstverbindung (streamState="connecting") zeigt keinen Reconnect-Banner', () => {
    const wrapper = mountFeed()
    // Bewusst VOR jedem await: onMounted() hat den Stream noch nicht
    // gestartet (streamStarted=false), streamState ist also 'connecting'.
    expect(wrapper.text()).not.toContain('feed.streamLost')
  })

  // §1: `since` filtert clientseitig gegen `timestamp` (Backend kennt den
  // Parameter weder fuer /feed-snapshot noch fuer den Stream).
  it('?since= filtert Beitraege vor dem Zeitstempel heraus', async () => {
    currentQuery = { since: '2026-05-15T12:00:05Z' }
    snapshotFeed = [
      mkPost({ post_id: 'before', timestamp: '2026-05-15T12:00:00Z' }),
      mkPost({ post_id: 'at', timestamp: '2026-05-15T12:00:05Z' }),
      mkPost({ post_id: 'after', timestamp: '2026-05-15T12:00:10Z' }),
    ]
    const wrapper = mountFeed()
    await flushPromises()

    expect(wrapper.findAll('.fi-root')).toHaveLength(2)
  })

  it('Klick auf einen Beitrag navigiert per router.push zu SimThreadFocus', async () => {
    snapshotFeed = [mkPost({ platform: 'reddit', post_id: 'snap-r-1' })]
    const wrapper = mountFeed()
    await flushPromises()

    await wrapper.get('.fi-root').trigger('click')

    expect(routerPushMock).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'SimThreadFocus',
        params: expect.objectContaining({ simulationId: 'test-sim-1', postId: 'snap-r-1' }),
      }),
    )
  })

  // Slice 9 · #1007 — kein clearSimFeed mehr in onBeforeUnmount.
  it('Unmount/Remount: Bestand bleibt erhalten (vor dem Fix wurde er beim Unmount geleert)', async () => {
    const wrapper1 = mountFeed()
    await flushPromises()

    for (let i = 0; i < 4; i++) {
      capturedPostCreatedHandler?.(mkPost({ platform: 'reddit', post_id: `u-${i}` }))
    }
    await flushPromises()

    expect(wrapper1.findAll('.fi-root')).toHaveLength(4)

    wrapper1.unmount()

    const wrapper2 = mountFeed()
    await flushPromises()

    expect(wrapper2.findAll('.fi-root')).toHaveLength(4)
  })
})
