import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const hoisted = await vi.hoisted(async () => {
  const { ref } = await import('vue')
  return {
    posts: ref<unknown[]>([]),
    loading: ref(false),
    error: ref<string | null>(null),
    truncated: ref(false),
    invalidCount: ref(0),
    evictedCount: ref(0),
    streamState: ref('live'),
    pendingCount: ref(0),
    roundCursor: ref<number | null>(null),
    maxRoundSeen: ref<number | null>(null),
    setRoundCursor: vi.fn(),
    flushPending: vi.fn(),
    reload: vi.fn(),
    stateKind: ref('running'),
    currentRound: ref<number | null>(null),
    totalRounds: ref<number | null>(24),
    adoptRunId: vi.fn(),
    contested: ref<string | null>('Soll es eine Abgabe geben?'),
    personaById: vi.fn(),
  }
})

vi.mock('@/composables/run/simulation/useRunFeed', async (importOriginal) => {
  const { computed: c } = await import('vue')
  const { postsUpToRound: upTo } = await import('@/composables/run/simulation/threads')
  return {
    ...(await importOriginal<object>()),
    useRunFeed: () => ({
      posts: hoisted.posts,
      visiblePosts: c(() => upTo(hoisted.posts.value as never[], hoisted.roundCursor.value)),
      loading: hoisted.loading,
      error: hoisted.error,
      truncated: hoisted.truncated,
      invalidCount: hoisted.invalidCount,
      evictedCount: hoisted.evictedCount,
      streamState: hoisted.streamState,
      pendingCount: hoisted.pendingCount,
      roundCursor: hoisted.roundCursor,
      maxRoundSeen: hoisted.maxRoundSeen,
      setRoundCursor: hoisted.setRoundCursor,
      flushPending: hoisted.flushPending,
      reload: hoisted.reload,
    }),
  }
})
vi.mock('@/composables/run/simulation/useRunPersonas', () => ({
  useRunPersonas: () => ({
    contestedQuestion: hoisted.contested,
    personaById: hoisted.personaById,
    loading: hoisted.loading,
    error: hoisted.error,
    reload: vi.fn(),
  }),
}))
vi.mock('@/composables/run/simulation/useSimulationRunState', () => ({
  useSimulationRunState: () => ({
    stateKind: hoisted.stateKind,
    currentRound: hoisted.currentRound,
    totalRounds: hoisted.totalRounds,
    adoptRunId: hoisted.adoptRunId,
  }),
}))

vi.mock('@/composables/run/simulation/useSimulationControl', async () => {
  const { ref } = await import('vue')
  return {
    useSimulationControl: () => ({
      busy: ref(null),
      error: ref(null),
      start: vi.fn(),
      plannedModel: () => 'std-model',
    }),
  }
})

import RunSimulationFeedView from '../RunSimulationFeedView.vue'
import { makePost } from '@/components/run/simulation/__tests__/fixtures'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
const Stub = defineComponent({ render: () => h('div', { 'data-testid': 'post-page' }) })

async function mountAt(path: string, stubs: Record<string, boolean> = { RunSimEmptyState: true }) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId/simulation/feed/:network(twitter|reddit)?',
        name: 'RunSimulationFeed',
        component: RunSimulationFeedView,
        props: true,
      },
      { path: '/simulations/:simulationId/simulation/post/:postId', name: 'RunSimulationPost', component: Stub, props: true },
    ],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(defineComponent({ render: () => h(RouterView) }), { global: { plugins: [router, i18n], stubs } })
  await flushPromises()
  return { w, router }
}

const BASE = '/simulations/sim_1/simulation/feed'

function seed(): PostCreatedEvent[] {
  return [
    makePost({ post_id: 'twitter:1', persona_id: '0', persona_name: 'Anna', body: 'Erster Beitrag', timestamp: '2026-10-01T10:00:00+00:00', round_num: 1, like_count: 3 }),
    makePost({ post_id: 'twitter:2', persona_id: '1', persona_name: 'Ben', body: 'Zweiter Beitrag zur Abgabe', timestamp: '2026-10-01T11:00:00+00:00', round_num: 2 }),
    makePost({ post_id: 'twitter:3', persona_id: '0', persona_name: 'Anna', kind: 'comment', parent_post_id: 'twitter:1', root_post_id: 'twitter:1', body: 'Antwort', timestamp: '2026-10-01T11:30:00+00:00', round_num: 2 }),
    makePost({ post_id: 'reddit:10', platform: 'reddit', persona_id: '1', persona_name: 'Ben', body: 'Reddit-Beitrag', score: 5, timestamp: '2026-10-01T12:00:00+00:00', round_num: 2 }),
    makePost({ post_id: 'reddit:comment:11', platform: 'reddit', kind: 'comment', parent_post_id: 'reddit:10', root_post_id: 'reddit:10', timestamp: '2026-10-01T12:10:00+00:00' }),
  ]
}

beforeEach(() => {
  hoisted.posts.value = seed()
  hoisted.loading.value = false
  hoisted.error.value = null
  hoisted.truncated.value = false
  hoisted.invalidCount.value = 0
  hoisted.evictedCount.value = 0
  hoisted.streamState.value = 'live'
  hoisted.pendingCount.value = 0
  hoisted.roundCursor.value = null
  hoisted.maxRoundSeen.value = 2
  hoisted.stateKind.value = 'running'
  hoisted.currentRound.value = null
  hoisted.totalRounds.value = 24
  hoisted.contested.value = 'Soll es eine Abgabe geben?'
  hoisted.personaById.mockReset()
  hoisted.personaById.mockReturnValue(null)
  hoisted.setRoundCursor.mockReset()
  hoisted.flushPending.mockReset()
  hoisted.reload.mockReset()
})

describe('RunSimulationFeedView', () => {
  it('zeigt standardmäßig Twitter, neueste oben, jeden Beitrag mit SIM-Kennzeichen und Zählern', async () => {
    const { w } = await mountAt(BASE)
    const cards = w.findAll('[data-testid="twitter-card"]')
    expect(cards.map((c) => c.attributes('data-post-id'))).toEqual(['twitter:2', 'twitter:1'])
    expect(w.findAll('[data-testid="post-sim"]')).toHaveLength(2)
    const first = cards[1]
    expect(first.get('[data-testid="count-replies"]').text()).toBe('eine Antwort')
    expect(first.get('[data-testid="count-likes"]').text()).toBe('3 Zustimmungen')
    expect(w.get('[data-testid="feed-network-twitter"]').attributes('aria-pressed')).toBe('true')
    expect(w.find('h1').exists()).toBe(false)
  })

  it('Netzwerkwechsel ändert die Adresse und zeigt die Reddit-Liste', async () => {
    const { w, router } = await mountAt(`${BASE}?q=Beitrag`)
    await w.get('[data-testid="feed-network-reddit"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.network).toBe('reddit')
    expect(router.currentRoute.value.query.q).toBe('Beitrag')
    const rows = w.findAll('[data-testid="reddit-row"]')
    expect(rows.map((r) => r.attributes('data-post-id'))).toEqual(['reddit:10'])
    expect(w.get('[data-testid="count-votes"]').text()).toBe('Stimmen: 5')
    expect(w.get('[data-testid="count-comments"]').text()).toBe('ein Kommentar')
  })

  it('liest die Filter aus der Query und schreibt Änderungen zurück', async () => {
    const { w, router } = await mountAt(`${BASE}/twitter?persona=1&q=abgabe`)
    expect(w.findAll('[data-testid="twitter-card"]').map((c) => c.attributes('data-post-id'))).toEqual(['twitter:2'])
    expect((w.get('[data-testid="feed-filter-persona"]').element as HTMLSelectElement).value).toBe('1')
    expect((w.get('[data-testid="feed-filter-query"]').element as HTMLInputElement).value).toBe('abgabe')

    await w.get('[data-testid="feed-filter-round"]').setValue('1')
    await flushPromises()
    expect(router.currentRoute.value.query.round).toBe('1')

    await w.get('[data-testid="feed-filter-reset"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect(w.findAll('[data-testid="twitter-card"]')).toHaveLength(2)
  })

  it('zeigt die Streitfrage als Text, nicht als Filter', async () => {
    const { w } = await mountAt(BASE)
    expect(w.get('[data-testid="feed-contested"]').text()).toContain('Soll es eine Abgabe geben?')
  })

  it('Klick auf einen Beitrag öffnet die Beitragsadresse mit Doppelpunkten und behält die Query', async () => {
    const { w, router } = await mountAt(`${BASE}?claim=twitter:1`)
    expect(w.get('[data-post-id="twitter:2"] [data-testid="twitter-card-link"]').attributes('href')).toContain(
      '/post/twitter:2?claim=twitter:1',
    )
    await w.get('[data-post-id="twitter:2"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunSimulationPost')
    expect(router.currentRoute.value.params.postId).toBe('twitter:2')
    expect(router.currentRoute.value.fullPath).toContain('/post/twitter:2')
    expect(router.currentRoute.value.query.claim).toBe('twitter:1')
  })

  it('Fokus auf einen Beitrag zeigt dessen Persona; fehlende Haltung wird genannt', async () => {
    hoisted.personaById.mockImplementation((id: string) =>
      id === '0'
        ? { personaId: '0', name: 'Anna Profil', username: null, role: 'Ärztin', bio: null, stance: null, contestedQuestion: null }
        : null,
    )
    const { w } = await mountAt(BASE)
    expect(w.find('[data-testid="persona-card-none"]').exists()).toBe(true)
    await w.get('[data-post-id="twitter:1"]').trigger('focus')
    expect(w.get('[data-testid="persona-card-name"]').text()).toBe('Anna Profil')
    expect(w.get('[data-testid="persona-card-stance"]').text()).toBe('Haltung nicht erfasst')
    expect(w.get('[data-testid="round-panel-title"]').text()).toBe('Runde 2 von 24')
  })

  it('Rundenregler ruft setRoundCursor, Pille ruft flushPending', async () => {
    hoisted.roundCursor.value = 1
    hoisted.pendingCount.value = 4
    const { w } = await mountAt(BASE)
    await w.get('[data-testid="scrubber-range"]').setValue('2')
    expect(hoisted.setRoundCursor).toHaveBeenCalledWith(2)
    await w.get('[data-testid="scrubber-live"]').trigger('click')
    expect(hoisted.setRoundCursor).toHaveBeenCalledWith(null)
    await w.get('[data-testid="scrubber-pill"]').trigger('click')
    expect(hoisted.flushPending).toHaveBeenCalledTimes(1)
  })

  it('zeigt beim Zurückgehen Beiträge ohne Rundenangabe als Hinweis', async () => {
    hoisted.posts.value = [
      ...seed(),
      makePost({ post_id: 'twitter:99', timestamp: '2026-10-01T09:00:00+00:00' }),
    ]
    hoisted.roundCursor.value = 1
    const { w } = await mountAt(BASE)
    expect(w.get('[data-testid="notice-unrounded"]').text()).toBe(
      '2 Beiträge ohne Rundenangabe werden in jeder Runde gezeigt.',
    )
    hoisted.roundCursor.value = null
    await flushPromises()
    expect(w.find('[data-testid="notice-unrounded"]').exists()).toBe(false)
  })

  it('zeigt Hinweise zu abgeschnittenem Snapshot, verworfenen und verdrängten Beiträgen', async () => {
    hoisted.truncated.value = true
    hoisted.invalidCount.value = 2
    hoisted.evictedCount.value = 9
    const { w } = await mountAt(BASE)
    expect(w.get('[data-testid="notice-truncated"]').text()).toContain('neuesten 5000 Beiträge je Netzwerk')
    expect(w.get('[data-testid="notice-invalid"]').text()).toContain('2 Beiträge')
    expect(w.get('[data-testid="notice-evicted"]').text()).toContain('9 ältere Beiträge')
  })

  it('zeigt einen Ladefehler als alert mit „Erneut laden"', async () => {
    hoisted.error.value = 'reddit: 502'
    const { w } = await mountAt(BASE)
    expect(w.get('[data-testid="notice-error"]').attributes('role')).toBe('alert')
    await w.get('[data-testid="notice-retry"]').trigger('click')
    expect(hoisted.reload).toHaveBeenCalledTimes(1)
  })

  it('meldet einen unterbrochenen Strom', async () => {
    hoisted.streamState.value = 'error'
    const { w } = await mountAt(BASE)
    expect(w.find('[data-testid="notice-stream"]').exists()).toBe(true)
  })

  it('zeigt Laden, Leerergebnis durch Filter und leeres Netzwerk', async () => {
    hoisted.posts.value = []
    hoisted.loading.value = true
    const loading = await mountAt(BASE)
    expect(loading.w.find('[data-testid="feed-loading"]').exists()).toBe(true)

    hoisted.loading.value = false
    const empty = await mountAt(BASE)
    expect(empty.w.get('[data-testid="feed-empty"]').text()).toContain('noch keine Beiträge')

    hoisted.posts.value = seed()
    const filtered = await mountAt(`${BASE}?q=gibtesnicht`)
    expect(filtered.w.get('[data-testid="feed-empty"]').text()).toBe('Kein Beitrag passt zu den Filtern.')
  })

  it('zeigt vor dem Start den Leerzustand statt des Feeds', async () => {
    hoisted.stateKind.value = 'notStarted'
    const { w } = await mountAt(BASE, { RunSimEmptyState: false })
    expect(w.find('[data-testid="sim-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="feed-list"]').exists()).toBe(false)
    expect(w.find('[data-testid="round-scrubber"]').exists()).toBe(false)
  })

  it('klappt die Seitenbereiche auf schmalen Breiten per Knopf mit aria-expanded', async () => {
    const { w } = await mountAt(BASE)
    const left = w.get('[data-testid="feed-toggle-left"]')
    expect(left.attributes('aria-expanded')).toBe('false')
    await left.trigger('click')
    expect(left.attributes('aria-expanded')).toBe('true')
    expect(w.get('#feed-left').classes()).not.toContain('feed__aside--collapsed')
  })
})
