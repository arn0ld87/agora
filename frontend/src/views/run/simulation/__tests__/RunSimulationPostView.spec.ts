import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

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
    reload: vi.fn(),
  }
})

vi.mock('@/composables/run/simulation/useRunFeed', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useRunFeed: () => hoisted,
}))

import RunSimulationPostView from '../RunSimulationPostView.vue'
import { makePost } from '@/components/run/simulation/__tests__/fixtures'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
const Stub = defineComponent({ render: () => h('div') })

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/simulations/:simulationId/simulation/feed/:network(twitter|reddit)?', name: 'RunSimulationFeed', component: Stub, props: true },
      { path: '/simulations/:simulationId/simulation/post/:postId', name: 'RunSimulationPost', component: RunSimulationPostView, props: true },
      { path: '/simulations/:simulationId/report/:reportId?', name: 'RunReport', component: Stub },
    ],
  })
  await router.push(path)
  await router.isReady()
  const w = mount(defineComponent({ render: () => h(RouterView) }), { global: { plugins: [router, i18n] } })
  await flushPromises()
  return { w, router }
}

const twitter = [
  makePost({ post_id: 'twitter:1', body: 'Wurzel', timestamp: '2026-10-01T10:00:00+00:00' }),
  makePost({ post_id: 'twitter:2', kind: 'comment', parent_post_id: 'twitter:1', root_post_id: 'twitter:1', body: 'Antwort A', timestamp: '2026-10-01T10:01:00+00:00' }),
  makePost({ post_id: 'twitter:3', kind: 'comment', parent_post_id: 'twitter:2', root_post_id: 'twitter:1', body: 'Antwort B', timestamp: '2026-10-01T10:02:00+00:00' }),
]
const reddit = (nested: boolean) => [
  makePost({ post_id: 'reddit:1', platform: 'reddit', body: 'Reddit-Beitrag', timestamp: '2026-10-01T10:00:00+00:00' }),
  makePost({ post_id: 'reddit:comment:2', platform: 'reddit', kind: 'comment', parent_post_id: 'reddit:1', root_post_id: 'reddit:1', body: 'K1', timestamp: '2026-10-01T10:01:00+00:00' }),
  makePost({
    post_id: 'reddit:comment:3', platform: 'reddit', kind: 'comment', parent_post_id: 'reddit:comment:2',
    parent_comment_id: nested ? 'reddit:comment:2' : null, root_post_id: 'reddit:1', body: 'K2', timestamp: '2026-10-01T10:02:00+00:00',
  }),
]

beforeEach(() => {
  hoisted.posts.value = twitter
  hoisted.loading.value = false
  hoisted.error.value = null
  hoisted.truncated.value = false
  hoisted.invalidCount.value = 0
  hoisted.evictedCount.value = 0
  hoisted.streamState.value = 'live'
  hoisted.reload.mockReset()
})

const P = '/simulations/sim_1/simulation/post'

describe('RunSimulationPostView', () => {
  it('Twitter: zeigt den Faden mit postId samt Doppelpunkt, ohne h1', async () => {
    const { w, router } = await mountAt(`${P}/twitter:1`)
    expect(router.currentRoute.value.params.postId).toBe('twitter:1')
    expect(w.get('[data-testid="thread-root"]').text()).toContain('Wurzel')
    expect(w.findAll('[data-testid="thread-node"]').map((n) => n.attributes('data-depth'))).toEqual(['1', '2'])
    expect(w.findAll('[data-testid="post-sim"]').length).toBeGreaterThanOrEqual(3)
    expect(w.find('h1').exists()).toBe(false)
  })

  it('Twitter: fehlende Wurzel als Hinweis', async () => {
    hoisted.posts.value = twitter.slice(1)
    const { w } = await mountAt(`${P}/twitter:2`)
    expect(w.get('[data-testid="thread-root-missing"]').text()).toBe(
      'Der Ausgangsbeitrag liegt außerhalb des geladenen Ausschnitts.',
    )
  })

  it('Twitter: fehlerhafte Kette als Fehlerhinweis', async () => {
    hoisted.posts.value = [
      makePost({ post_id: 'twitter:a', kind: 'comment', parent_post_id: 'twitter:b' }),
      makePost({ post_id: 'twitter:b', kind: 'comment', parent_post_id: 'twitter:a' }),
    ]
    const { w } = await mountAt(`${P}/twitter:a`)
    expect(w.get('[data-testid="thread-broken"]').attributes('role')).toBe('alert')
  })

  it('Reddit: Netzwerk aus dem Präfix, Baum mit einklappbarem Ast per aria-expanded', async () => {
    hoisted.posts.value = reddit(true)
    const { w } = await mountAt(`${P}/reddit:1`)
    expect(w.get('[data-testid="reddit-root"]').text()).toContain('Reddit-Beitrag')
    const toggle = w.get('[data-testid="reddit-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(w.find('[data-testid="tree-flat-only"]').exists()).toBe(false)
  })

  it('Reddit: flache Kommentare zeigen den Datenlücken-Hinweis', async () => {
    hoisted.posts.value = reddit(false)
    const { w } = await mountAt(`${P}/reddit:1`)
    expect(w.get('[data-testid="tree-flat-only"]').text()).toBe(
      'Dieser Lauf enthält keine Verschachtelung der Kommentare. Alle Kommentare stehen flach unter dem Beitrag.',
    )
  })

  it('Reddit: fehlender Beitrag wird gemeldet', async () => {
    hoisted.posts.value = reddit(true).slice(1)
    const { w } = await mountAt(`${P}/reddit:1`)
    expect(w.find('[data-testid="tree-root-missing"]').exists()).toBe(true)
  })

  it('„Zurück zum Bericht" nur mit ?fromClaim=, trägt die Fassung; ?claim= bleibt die post_id', async () => {
    const plain = await mountAt(`${P}/twitter:1?claim=twitter:1`)
    expect(plain.w.find('[data-testid="post-back-report"]').exists()).toBe(false)

    const { w } = await mountAt(`${P}/twitter:1?claim=twitter:1&fromClaim=claim_01&report=report_7`)
    const back = w.get('[data-testid="post-back-report"]')
    expect(back.text()).toBe('Zurück zum Bericht')
    expect(back.attributes('href')).toBe('/simulations/sim_1/report/report_7?claim=claim_01')
    expect(w.find('[data-testid="thread-claim"]').exists()).toBe(true)

    const noReport = await mountAt(`${P}/twitter:1?claim=twitter:1&fromClaim=claim_01`)
    expect(noReport.w.get('[data-testid="post-back-report"]').attributes('href')).toBe('/simulations/sim_1/report?claim=claim_01')
  })

  it('„Zurück zum Feed" behält Netzwerk und Filter', async () => {
    hoisted.posts.value = reddit(true)
    const { w, router } = await mountAt(`${P}/reddit:1?persona=1&q=abc`)
    const back = w.get('[data-testid="post-back"]')
    expect(back.attributes('href')).toBe('/simulations/sim_1/simulation/feed/reddit?persona=1&q=abc')
    await back.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunSimulationFeed')
    expect(router.currentRoute.value.params.network).toBe('reddit')
  })

  it('erhält ?claim= und hebt den Beitrag hervor', async () => {
    const { w, router } = await mountAt(`${P}/twitter:1?claim=twitter:3`)
    expect(router.currentRoute.value.query.claim).toBe('twitter:3')
    const marked = w.findAll('[aria-current="true"]')
    expect(marked).toHaveLength(1)
    expect(marked[0].text()).toContain('Antwort B')
    expect(w.get('[data-testid="post-back"]').attributes('href')).toContain('claim=twitter:3')
  })

  it('zeigt Laden und Fehler sichtbar', async () => {
    hoisted.posts.value = []
    hoisted.loading.value = true
    const loading = await mountAt(`${P}/twitter:1`)
    expect(loading.w.find('[data-testid="post-loading"]').exists()).toBe(true)

    hoisted.loading.value = false
    hoisted.error.value = 'twitter: 500'
    const failed = await mountAt(`${P}/twitter:1`)
    expect(failed.w.get('[data-testid="notice-error"]').attributes('role')).toBe('alert')
    await failed.w.get('[data-testid="notice-retry"]').trigger('click')
    expect(hoisted.reload).toHaveBeenCalled()
  })
})
