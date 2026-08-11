/**
 * StepSimulationFeedView — Vitest-Smoke-Tests.
 *
 * Slice FE-Redesign-5 · 2026-05-15
 *
 * Prueft:
 * 1. Mock-Stream injiziert Posts → useSimFeed empfängt sie.
 * 2. Reddit-Count stimmt nach 5 Reddit-Posts.
 * 3. Twitter-Count stimmt nach 3 Twitter-Posts.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createRouter, createMemoryHistory } from 'vue-router'
import { resetSimFeedStore } from '@/composables/useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

// ---- Mocks ----

// useEventStream mocken: Wir speichern den post_created-Handler und können
// ihn im Test manuell triggern.
let capturedPostCreatedHandler: ((data: PostCreatedEvent) => void) | undefined

// #1009 — Snapshot-Fetch beim Mount mocken. Wir zeichnen die Aufrufe auf,
// um zu verifizieren, dass die View beide Plattformen lädt, ohne echte
// HTTP-Requests abzusetzen. `snapshotFeed` steuert den Rückgabewert pro
// Plattform; default ist leer.
let snapshotFetchCalls: { simulationId: string; platform: string }[] = []
let snapshotFeed: PostCreatedEvent[] = []

// Reihenfolge-Tracker: Race-Condition-Regression (#1009 Codex-Finding).
// start() muss VOR dem ersten Snapshot-Fetch aufgerufen werden, sonst geht
// ein Post verloren, der zwischen Snapshot-Read und stream.start() geschrieben
// wird (post_created hat kein Replay). Ein globaler Zähler fixiert die
// Aufrufreihenfolge unabhängig von Timern.
let callOrder = 0
let streamStartOrder = -1
let snapshotFirstFetchOrder = -1

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshot: (simulationId: string, platform: string) => {
    if (snapshotFirstFetchOrder === -1) snapshotFirstFetchOrder = callOrder++
    snapshotFetchCalls.push({ simulationId, platform })
    return Promise.resolve(snapshotFeed.filter((p) => p.platform === platform))
  },
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

// Sub-Komponenten stubben für Isolation
vi.mock('@/components/v4/sim-feed/FeedColumn.vue', () => ({
  default: {
    name: 'FeedColumn',
    props: ['title', 'channel'],
    template: '<section :data-channel="channel"><slot /></section>',
  },
}))
vi.mock('@/components/v4/sim-feed/SimulationPulseBar.vue', () => ({
  default: {
    name: 'SimulationPulseBar',
    props: ['activityRate', 'redditCount', 'twitterCount'],
    template: '<div class="pulse-bar" :data-reddit="redditCount" :data-twitter="twitterCount" />',
  },
}))
vi.mock('@/components/v4/sim-feed/RedditThread.vue', () => ({
  default: {
    name: 'RedditThread',
    props: ['node', 'depth'],
    template: '<div class="reddit-thread-stub" :data-id="node.post_id">{{ node.body }}</div>',
  },
}))
vi.mock('@/components/v4/sim-feed/TwitterPost.vue', () => ({
  default: {
    name: 'TwitterPost',
    props: ['post'],
    template: '<article class="twitter-post-stub" :data-id="post.post_id">{{ post.body }}</article>',
  },
}))

// useRoute mocken
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { simulationId: 'test-sim-1' } }),
  }
})

// useSimFeed batcht eingehende Posts pro Animation Frame (#1007). jsdoms
// requestAnimationFrame loest erst nach ~16ms Realzeit aus; die Tests unten
// pruefen den Feed-State direkt nach dem synchronen Handler-Aufruf ohne auf
// einen echten Frame zu warten. Globaler Stub macht rAF synchron, damit
// bestehende Assertions unveraendert bleiben.
vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  cb(0)
  return 0
})

import StepSimulationFeedView from '../StepSimulationFeedView.vue'

// ---- i18n ----
const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      feed: {
        reddit: 'Reddit',
        twitter: 'Twitter',
        simBadge: 'SIM',
        activity: 'Posts/min',
        live: 'Live',
        empty: 'Noch keine Aktivität.',
      },
      common: { scrollToBottom: 'Zum aktuellen Beitrag springen' },
    },
  },
})

// ---- Router ----
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    {
      path: '/v4/simulation/:simulationId/feed',
      name: 'StepSimulationFeed',
      component: StepSimulationFeedView,
    },
  ],
})

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
  })

  it('mountet ohne Crash und stellt Stream auf', async () => {
    const wrapper = mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
  })

  it('#1009: holt Feed-Snapshot für reddit und twitter beim Mount', async () => {
    mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()
    const platforms = snapshotFetchCalls.map((c) => c.platform).sort()
    expect(platforms).toEqual(['reddit', 'twitter'])
    expect(snapshotFetchCalls.every((c) => c.simulationId === 'test-sim-1')).toBe(true)
  })

  it('#1009: startet den Stream VOR dem Snapshot-Fetch (Race-Condition, Codex-Finding)', async () => {
    // post_created hat kein Replay: ein Post, der zwischen Snapshot-Read und
    // stream.start() geschrieben wird, fehlt im Snapshot UND vor start() gibt
    // es keinen Listener. Also muss start() zuerst kommen; die seen-Dedup
    // fängt den Overlap ab. Vor dem Fix stand stream.start() NACH dem Fetch.
    mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()
    expect(streamStartOrder).toBeGreaterThanOrEqual(0)
    expect(snapshotFirstFetchOrder).toBeGreaterThanOrEqual(0)
    expect(streamStartOrder).toBeLessThan(snapshotFirstFetchOrder)
  })

  it('#1009: Snapshot-Posts werden beim Mount in den Feed ingestiert', async () => {
    // Snapshot liefert einen Reddit- und einen Twitter-Post; der Mock gibt
    // plattformgefiltert zurück.
    snapshotFeed = [
      mkPost({ platform: 'reddit', post_id: 'snap-r-1' }),
      mkPost({ platform: 'twitter', post_id: 'snap-t-1' }),
    ]

    const wrapper = mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()

    const pulseBar = wrapper.find('.pulse-bar')
    expect(Number(pulseBar.attributes('data-reddit'))).toBe(1)
    expect(Number(pulseBar.attributes('data-twitter'))).toBe(1)
  })

  it('Reddit-Count: 5 Reddit-Posts kommen in RedditThread-Stubs an', async () => {
    const wrapper = mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()

    // 5 Reddit-Posts injizieren
    for (let i = 0; i < 5; i++) {
      capturedPostCreatedHandler?.(mkPost({ platform: 'reddit', post_id: `r-${i}` }))
    }
    await flushPromises()

    const pulseBar = wrapper.find('.pulse-bar')
    expect(Number(pulseBar.attributes('data-reddit'))).toBe(5)
    expect(Number(pulseBar.attributes('data-twitter'))).toBe(0)
  })

  it('Twitter-Count: 3 Twitter-Posts kommen in TwitterPost-Stubs an', async () => {
    const wrapper = mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()

    for (let i = 0; i < 3; i++) {
      capturedPostCreatedHandler?.(mkPost({ platform: 'twitter', post_id: `t-${i}` }))
    }
    await flushPromises()

    const pulseBar = wrapper.find('.pulse-bar')
    expect(Number(pulseBar.attributes('data-twitter'))).toBe(3)
    expect(Number(pulseBar.attributes('data-reddit'))).toBe(0)
  })

  // Slice 9 · #1007 — kein clearSimFeed mehr in onBeforeUnmount.
  it('Unmount/Remount: Bestand bleibt erhalten (vor dem Fix wurde er beim Unmount geleert)', async () => {
    const wrapper1 = mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()

    for (let i = 0; i < 4; i++) {
      capturedPostCreatedHandler?.(mkPost({ platform: 'reddit', post_id: `u-${i}` }))
    }
    await flushPromises()

    expect(Number(wrapper1.find('.pulse-bar').attributes('data-reddit'))).toBe(4)

    wrapper1.unmount()

    const wrapper2 = mount(StepSimulationFeedView, {
      global: { plugins: [i18n, router] },
    })
    await flushPromises()

    expect(Number(wrapper2.find('.pulse-bar').attributes('data-reddit'))).toBe(4)
  })
})
