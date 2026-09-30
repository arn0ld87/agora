/**
 * SimThreadsView — Slice UI-2b (#1713), Commit 4
 * (docs/design/simulation-feed.md §2.7).
 *
 * Prueft: Snapshot-Ladung fuer beide Plattformen, Gruppierung zu
 * Strang-Zeilen (SimThreadList), Such-Filter (q) engt die Liste ein,
 * Klick auf einen Strang navigiert per router.push zu SimThreadFocus.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { resetSimFeedStore } from '@/composables/useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

let capturedPostCreatedHandler: ((data: PostCreatedEvent) => void) | undefined
let snapshotFetchCalls: { simulationId: string; platform: string }[] = []
let snapshotFeed: PostCreatedEvent[] = []

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshot: (simulationId: string, platform: string) => {
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
      start: vi.fn(() => Promise.resolve()),
      stop: vi.fn(),
    }
  },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

const routerPushMock = vi.fn()
let currentQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { simulationId: 'test-sim-threads' }, query: currentQuery }),
  useRouter: () => ({ push: routerPushMock, replace: vi.fn() }),
}))

// useSimFeed batcht eingehende Posts pro Animation Frame (#1007); rAF-Stub
// macht den Flush synchron (siehe StepSimulationFeedView.spec.ts).
vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  cb(0)
  return 0
})

import SimThreadsView from '../SimThreadsView.vue'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'test-sim-threads',
    post_id: `p-${Math.random().toString(36).slice(2)}`,
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    persona_name: 'Alice',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'Test',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    kind: 'post',
    ...overrides,
  }
}

describe('SimThreadsView', () => {
  beforeEach(() => {
    resetSimFeedStore('test-sim-threads')
    capturedPostCreatedHandler = undefined
    snapshotFetchCalls = []
    snapshotFeed = []
    currentQuery = {}
    routerPushMock.mockClear()
  })

  it('holt den Snapshot fuer beide Plattformen beim Mount', async () => {
    mount(SimThreadsView)
    await flushPromises()
    expect(snapshotFetchCalls.map((c) => c.platform).sort()).toEqual(['reddit', 'twitter'])
  })

  it('leerer Strang-Bestand zeigt den Empty-State (no_data)', async () => {
    const w = mount(SimThreadsView)
    await flushPromises()
    expect(w.text()).toContain('feed.threadList.empty')
  })

  it('Strang-Wurzeln aus dem Snapshot werden als Zeilen gruppiert', async () => {
    snapshotFeed = [
      mkPost({ post_id: 'root-1', kind: 'post' }),
      mkPost({ post_id: 'reply-1', kind: 'comment', parent_post_id: 'root-1', root_post_id: 'root-1' }),
      mkPost({ post_id: 'root-2', kind: 'post', platform: 'twitter' }),
    ]
    const w = mount(SimThreadsView)
    await flushPromises()
    expect(w.findAll('.stl2-item')).toHaveLength(2)
  })

  it('neue Posts aus dem Stream landen ebenfalls in der Strang-Liste', async () => {
    const w = mount(SimThreadsView)
    await flushPromises()
    capturedPostCreatedHandler?.(mkPost({ post_id: 'live-root', kind: 'post' }))
    await flushPromises()
    expect(w.findAll('.stl2-item')).toHaveLength(1)
  })

  it('Klick auf einen Strang navigiert per router.push zu SimThreadFocus', async () => {
    snapshotFeed = [mkPost({ post_id: 'root-click', kind: 'post' })]
    const w = mount(SimThreadsView)
    await flushPromises()
    await w.get('[role="button"]').trigger('click')
    expect(routerPushMock).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'SimThreadFocus',
        params: expect.objectContaining({ simulationId: 'test-sim-threads', postId: 'root-click' }),
      }),
    )
  })
})
