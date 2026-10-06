/**
 * SimThreadFocusView — Slice UI-2b (#1713), Commit 4
 * (docs/design/simulation-feed.md §2.8).
 *
 * Prueft: Wurzel wird aus dem Feed-Store aufgeloest (Snapshot-Ladung nur,
 * wenn der Store noch leer ist), Strang-Knoten werden an SimThreadTree
 * durchgereicht, unbekannte postId zeigt den Placeholder, Esc navigiert
 * route-basiert zurueck zum Feed (RunSimulationFeed).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { resetSimFeedStore, useSimFeed } from '@/composables/useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

let capturedPostCreatedHandler: ((data: PostCreatedEvent) => void) | undefined
let snapshotFetchCalls: { simulationId: string; platform: string }[] = []
let snapshotFeed: PostCreatedEvent[] = []

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshot: (simulationId: string, platform: string) => {
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
      start: vi.fn(() => Promise.resolve()),
      stop: vi.fn(),
    }
  },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

const routerPushMock = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { simulationId: 'test-sim-focus' }, query: {} }),
  useRouter: () => ({ push: routerPushMock, replace: vi.fn() }),
}))

vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  cb(0)
  return 0
})

import SimThreadFocusView from '../SimThreadFocusView.vue'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'test-sim-focus',
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

describe('SimThreadFocusView', () => {
  beforeEach(() => {
    resetSimFeedStore('test-sim-focus')
    capturedPostCreatedHandler = undefined
    snapshotFetchCalls = []
    snapshotFeed = []
    routerPushMock.mockClear()
  })

  it('unbekannte postId zeigt den Placeholder-Text, ohne zu crashen', async () => {
    // Zwei role="status"-Elemente sind im Baum (SimRunHeader + Placeholder);
    // die spezifische Klasse zielt eindeutig auf den Platzhalter.
    const w = mount(SimThreadFocusView, { props: { postId: 'missing' } })
    await flushPromises()
    expect(w.get('.stf-empty').text()).toBe('feed.threadFocusPlaceholder')
  })

  it('laedt den Snapshot, wenn der Store noch leer ist', async () => {
    snapshotFeed = [mkPost({ post_id: 'root-1', kind: 'post' })]
    mount(SimThreadFocusView, { props: { postId: 'root-1' } })
    await flushPromises()
    expect(snapshotFetchCalls.map((c) => c.platform).sort()).toEqual(['reddit', 'twitter'])
  })

  it('laedt KEINEN Snapshot, wenn der Store bereits gefuellt ist (Wechsel von Feed/Diskurs)', async () => {
    const feed = useSimFeed('test-sim-focus')
    feed.ingest(mkPost({ post_id: 'already-there', kind: 'post' }))
    feed.flushPending()

    mount(SimThreadFocusView, { props: { postId: 'already-there' } })
    await flushPromises()
    expect(snapshotFetchCalls).toHaveLength(0)
  })

  it('rendert die Wurzel und ihre Antworten ueber SimThreadTree', async () => {
    const feed = useSimFeed('test-sim-focus')
    feed.ingestMany([
      mkPost({ post_id: 'root-1', kind: 'post' }),
      mkPost({ post_id: 'reply-1', kind: 'comment', parent_post_id: 'root-1', root_post_id: 'root-1' }),
    ])

    const w = mount(SimThreadFocusView, { props: { postId: 'root-1' } })
    await flushPromises()

    expect(w.findAll('.fi-root')).toHaveLength(2)
  })

  it('ein live nachgereichter Post erscheint im Strang', async () => {
    const feed = useSimFeed('test-sim-focus')
    feed.ingest(mkPost({ post_id: 'root-1', kind: 'post' }))
    feed.flushPending()

    const w = mount(SimThreadFocusView, { props: { postId: 'root-1' } })
    await flushPromises()
    expect(w.findAll('.fi-root')).toHaveLength(1)

    capturedPostCreatedHandler?.(
      mkPost({ post_id: 'live-reply', kind: 'comment', parent_post_id: 'root-1', root_post_id: 'root-1' }),
    )
    await flushPromises()
    expect(w.findAll('.fi-root')).toHaveLength(2)
  })

  it('Esc navigiert route-basiert zurueck zu SimThreads', async () => {
    const feed = useSimFeed('test-sim-focus')
    feed.ingest(mkPost({ post_id: 'root-1', kind: 'post' }))
    feed.flushPending()

    const w = mount(SimThreadFocusView, { props: { postId: 'root-1' } })
    await flushPromises()

    await w.get('.stf-root').trigger('keydown', { key: 'Escape' })
    expect(routerPushMock).toHaveBeenCalledWith(expect.objectContaining({ name: 'RunSimulationFeed' }))
  })
})
