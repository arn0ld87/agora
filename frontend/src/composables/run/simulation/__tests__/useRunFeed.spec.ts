import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref, type Ref } from 'vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const hoisted = vi.hoisted(() => ({
  handlers: null as null | { post_created?: (p: unknown) => void },
  start: vi.fn(),
  stop: vi.fn(),
  isStreaming: { value: false },
  streamError: { value: null as unknown },
  page: vi.fn(),
}))

vi.mock('@/composables/useEventStream', async () => {
  const { ref: vueRef } = await import('vue')
  return {
    useEventStream: (_id: unknown, handlers: { post_created?: (p: unknown) => void }) => {
      hoisted.handlers = handlers
      const isStreaming = vueRef(false)
      const error = vueRef<unknown>(null)
      hoisted.isStreaming = isStreaming
      hoisted.streamError = error
      return {
        isStreaming,
        error,
        lastEventAt: vueRef(null),
        lastTraceId: vueRef(null),
        start: async () => {
          hoisted.start()
          isStreaming.value = true
        },
        stop: () => {
          hoisted.stop()
          isStreaming.value = false
        },
      }
    },
  }
})

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshotPage: hoisted.page,
}))

import { FEED_SNAPSHOT_LIMIT, RUN_FEED_MAX_POSTS, useRunFeed } from '../useRunFeed'

let n = 0
function mk(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  n += 1
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: `twitter:${n}`,
    parent_post_id: null,
    platform: 'twitter',
    persona_id: '0',
    persona_name: 'Anna',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'text',
    timestamp: new Date(Date.UTC(2026, 0, 1, 12, 0, 0) + n * 1000).toISOString(),
    score: 0,
    ...overrides,
  }
}

function page(posts: PostCreatedEvent[], extra: Partial<{ receivedCount: number; invalidCount: number }> = {}) {
  return { posts, receivedCount: posts.length, invalidCount: 0, ...extra }
}

async function flush(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve()
  await nextTick()
}

function setup(id: string | Ref<string> = 'sim-1') {
  const scope = effectScope()
  const feed = scope.run(() => useRunFeed(id))!
  return { feed, scope }
}

beforeEach(() => {
  hoisted.start.mockClear()
  hoisted.stop.mockClear()
  hoisted.page.mockReset()
  hoisted.page.mockResolvedValue(page([]))
})

describe('useRunFeed', () => {
  it('lädt beide Netzwerke mit hohem limit und mischt chronologisch', async () => {
    const a = mk({ platform: 'twitter' })
    const b = mk({ platform: 'reddit', post_id: 'reddit:1' })
    hoisted.page.mockImplementation(async (_id: string, platform: string) =>
      platform === 'twitter' ? page([a]) : page([b]),
    )
    const { feed } = setup()
    await flush()

    expect(hoisted.page).toHaveBeenCalledWith('sim-1', 'twitter', { limit: FEED_SNAPSHOT_LIMIT })
    expect(hoisted.page).toHaveBeenCalledWith('sim-1', 'reddit', { limit: FEED_SNAPSHOT_LIMIT })
    expect(feed.posts.value.map((p) => p.post_id)).toEqual([a.post_id, 'reddit:1'])
    expect(feed.loading.value).toBe(false)
    expect(feed.error.value).toBeNull()
    expect(feed.truncated.value).toBe(false)
  })

  it('truncated, wenn ein Snapshot genau limit Einträge lieferte (auch bei verworfenen)', async () => {
    hoisted.page.mockImplementation(async (_id: string, platform: string) =>
      platform === 'twitter'
        ? page([mk()], { receivedCount: FEED_SNAPSHOT_LIMIT, invalidCount: 2 })
        : page([]),
    )
    const { feed } = setup()
    await flush()
    expect(feed.truncated.value).toBe(true)
    expect(feed.invalidCount.value).toBe(2)
  })

  it('zeigt einen Snapshot-Fehler sichtbar, behält aber das andere Netzwerk', async () => {
    const ok = mk({ platform: 'reddit', post_id: 'reddit:1' })
    hoisted.page.mockImplementation(async (_id: string, platform: string) => {
      if (platform === 'twitter') throw new Error('boom')
      return page([ok])
    })
    const { feed } = setup()
    await flush()
    expect(feed.error.value).toContain('twitter')
    expect(feed.error.value).toContain('boom')
    expect(feed.posts.value).toHaveLength(1)
    expect(feed.loading.value).toBe(false)
  })

  it('dedupliziert Live-Beiträge gegen den Snapshot und gegen sich selbst', async () => {
    const a = mk()
    hoisted.page.mockImplementation(async (_id: string, platform: string) =>
      platform === 'twitter' ? page([a]) : page([]),
    )
    const { feed } = setup()
    await flush()

    hoisted.handlers!.post_created!(a)
    const live = mk()
    hoisted.handlers!.post_created!(live)
    hoisted.handlers!.post_created!(live)
    expect(feed.posts.value.map((p) => p.post_id)).toEqual([a.post_id, live.post_id])
  })

  it('ignoriert Beiträge einer anderen Simulation', async () => {
    const { feed } = setup()
    await flush()
    hoisted.handlers!.post_created!(mk({ simulation_id: 'sim-other' }))
    expect(feed.posts.value).toHaveLength(0)
  })

  it('sammelt im Rückblick-Modus und übernimmt per flushPending', async () => {
    const { feed } = setup()
    await flush()
    feed.setRoundCursor(3)
    hoisted.handlers!.post_created!(mk({ round_num: 5 }))
    hoisted.handlers!.post_created!(mk({ round_num: 6 }))
    expect(feed.pendingCount.value).toBe(2)
    expect(feed.posts.value).toHaveLength(0)
    expect(feed.maxRoundSeen.value).toBeNull()

    feed.flushPending()
    expect(feed.pendingCount.value).toBe(0)
    expect(feed.posts.value).toHaveLength(2)
    expect(feed.maxRoundSeen.value).toBe(6)
    // Weiterhin im Rückblick: sichtbar nur bis Runde 3.
    expect(feed.visiblePosts.value).toHaveLength(0)
  })

  it('kehrt mit setRoundCursor(null) zu live zurück und übernimmt Gesammeltes', async () => {
    const { feed } = setup()
    await flush()
    feed.setRoundCursor(1)
    hoisted.handlers!.post_created!(mk({ round_num: 2 }))
    feed.setRoundCursor(null)
    expect(feed.pendingCount.value).toBe(0)
    expect(feed.visiblePosts.value).toHaveLength(1)
    expect(feed.roundCursor.value).toBeNull()
  })

  it('verdrängt die ältesten Beiträge an der Obergrenze und zählt sie', async () => {
    const { feed } = setup()
    await flush()
    const first = mk()
    hoisted.handlers!.post_created!(first)
    for (let i = 0; i < RUN_FEED_MAX_POSTS; i++) hoisted.handlers!.post_created!(mk())
    expect(feed.posts.value).toHaveLength(RUN_FEED_MAX_POSTS)
    expect(feed.evictedCount.value).toBe(1)
    expect(feed.posts.value.some((p) => p.post_id === first.post_id)).toBe(false)
    // Ein verdrängter Beitrag darf später erneut eintreffen.
    hoisted.handlers!.post_created!(first)
    expect(feed.posts.value.some((p) => p.post_id === first.post_id)).toBe(true)
  })

  it('streamState folgt dem Strom', async () => {
    const { feed } = setup()
    await flush()
    expect(feed.streamState.value).toBe('live')
    hoisted.isStreaming.value = false
    expect(feed.streamState.value).toBe('connecting')
    hoisted.isStreaming.value = false
    hoisted.streamError.value = new Error('x')
    expect(feed.streamState.value).toBe('error')
  })

  it('immediate: false lädt nichts, bis start() läuft', async () => {
    const scope = effectScope()
    const feed = scope.run(() => useRunFeed('sim-1', { immediate: false }))!
    await flush()
    expect(hoisted.page).not.toHaveBeenCalled()
    expect(feed.streamState.value).toBe('idle')
    await feed.start()
    expect(hoisted.page).toHaveBeenCalledTimes(2)
  })

  it('räumt beim Scope-Ende auf und schließt den Strom', async () => {
    const { scope } = setup()
    await flush()
    scope.stop()
    expect(hoisted.stop).toHaveBeenCalled()
  })

  it('Kennungswechsel: Strom schließen, Puffer leeren, neu laden', async () => {
    const id = ref('sim-1')
    const a = mk()
    hoisted.page.mockImplementation(async (simId: string, platform: string) =>
      platform === 'twitter' && simId === 'sim-1' ? page([a]) : page([]),
    )
    const { feed } = setup(id)
    await flush()
    expect(feed.posts.value).toHaveLength(1)

    id.value = 'sim-2'
    await flush()
    expect(hoisted.stop).toHaveBeenCalled()
    expect(feed.posts.value).toHaveLength(0)
    expect(hoisted.page).toHaveBeenCalledWith('sim-2', 'twitter', { limit: FEED_SNAPSHOT_LIMIT })
    // Beiträge der alten Simulation werden danach nicht mehr aufgenommen.
    hoisted.handlers!.post_created!(mk({ simulation_id: 'sim-1' }))
    expect(feed.posts.value).toHaveLength(0)
  })

  it('verwirft eine veraltete Snapshot-Antwort nach Kennungswechsel', async () => {
    const id = ref('sim-1')
    let release: (v: ReturnType<typeof page>) => void = () => {}
    hoisted.page.mockImplementationOnce(
      () => new Promise((resolve) => (release = resolve as typeof release)),
    )
    hoisted.page.mockResolvedValue(page([]))
    const { feed } = setup(id)
    await flush()
    id.value = 'sim-2'
    await flush()
    release(page([mk()]))
    await flush()
    expect(feed.posts.value).toHaveLength(0)
  })

  it('reload ergänzt fehlende Beiträge, ohne Bekanntes zu duplizieren', async () => {
    const a = mk()
    const b = mk()
    hoisted.page.mockImplementation(async (_id: string, platform: string) =>
      platform === 'twitter' ? page([a]) : page([]),
    )
    const { feed } = setup()
    await flush()
    hoisted.page.mockImplementation(async (_id: string, platform: string) =>
      platform === 'twitter' ? page([a, b]) : page([]),
    )
    await feed.reload()
    expect(feed.posts.value.map((p) => p.post_id)).toEqual([a.post_id, b.post_id])
  })
})
