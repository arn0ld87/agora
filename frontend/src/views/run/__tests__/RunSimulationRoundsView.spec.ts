import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

const h_ = await vi.hoisted(async () => {
  const { ref, computed } = await import('vue')
  const kind = ref<string>('done')
  return {
    kind,
    state: {
      stateKind: computed(() => kind.value),
      currentRound: ref<number | null>(2),
      totalRounds: ref<number | null>(3),
    },
    getRounds: vi.fn(),
    getActions: vi.fn(),
  }
})

vi.mock('@/composables/run/simulation/useSimulationRunState', () => ({ useSimulationRunState: () => h_.state }))
vi.mock('@/api/simulation', () => ({
  getSimulationRounds: (...a: unknown[]) => h_.getRounds(...a),
  getSimulationActions: (...a: unknown[]) => h_.getActions(...a),
}))

import RunSimulationRoundsView from '../simulation/RunSimulationRoundsView.vue'

const Stub = defineComponent({ render: () => h('div') })
const ROUNDS = {
  success: true,
  data: {
    rounds: [
      { round_num: 0, platform: 'twitter', action_counts: { CREATE_POST: 2 } },
      { round_num: 1, platform: 'twitter', action_counts: { CREATE_POST: 3, LIKE_POST: 1 } },
      { round_num: 1, platform: 'reddit', action_counts: { CREATE_COMMENT: 4 } },
      { round_num: 2, platform: 'reddit', action_counts: {} },
    ],
  },
}
const ACTIONS = {
  success: true,
  data: {
    items: [
      {
        round_num: 1, timestamp: '2026-10-07T10:00:00Z', agent_id: '1', agent_name: 'Anna', platform: 'twitter',
        action_type: 'LIKE_POST', content: null, target_post_id: 'twitter:post:42', success: true,
      },
    ],
    next_cursor: null,
  },
}

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId/simulation',
        component: RouterView,
        children: [
          { path: 'feed/:network(twitter|reddit)?', name: 'RunSimulationFeed', component: Stub },
          { path: 'post/:postId', name: 'RunSimulationPost', component: Stub },
          { path: 'rounds', name: 'RunSimulationRounds', component: RunSimulationRoundsView, props: true },
        ],
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  const w = mount(RouterView, { global: { plugins: [router, i18n] }, attachTo: document.body })
  await flushPromises()
  return { router, w }
}

const BASE = '/simulations/sim_1/simulation/rounds'

beforeEach(() => {
  document.body.innerHTML = ''
  h_.kind.value = 'done'
  h_.state.currentRound.value = 2
  h_.state.totalRounds.value = 3
  h_.getRounds.mockReset().mockResolvedValue(ROUNDS)
  h_.getActions.mockReset().mockResolvedValue(ACTIONS)
})

describe('RunSimulationRoundsView', () => {
  it('zeigt Runden mit Aktivität je Netzwerk, "Runde x von y" und Startbeiträge', async () => {
    const { w } = await mountAt(BASE)
    expect(w.find('[data-testid="round-0"]').text()).toContain('Startbeiträge')
    const r1 = w.find('[data-testid="round-1"]').text()
    expect(r1).toContain('Runde 1 von 3')
    expect(r1).toContain('Twitter')
    expect(r1).toContain('Reddit')
    expect(r1).toContain('Beiträge: 3')
    expect(w.find('[data-testid="round-2"]').text()).toContain('Keine Aktionen')
  })

  it('kennzeichnet die laufende Runde nur bei laufendem Lauf', async () => {
    h_.kind.value = 'running'
    const { w } = await mountAt(BASE)
    expect(w.find('[data-testid="round-2"]').attributes('aria-current')).toBe('step')
    expect(w.find('[data-testid="round-1"]').attributes('aria-current')).toBeUndefined()
    expect(w.find('[data-testid="round-2"]').text()).toContain('läuft')
  })

  it('verlinkt je Netzwerk in den Feed mit Runde', async () => {
    const { w, router } = await mountAt(BASE)
    const link = w.find('[data-testid="round-1-feed-reddit"]')
    expect(link.attributes('href')).toBe('/simulations/sim_1/simulation/feed/reddit?round=1')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunSimulationFeed')
    expect(router.currentRoute.value.params.network).toBe('reddit')
    expect(router.currentRoute.value.query.round).toBe('1')
  })

  it('zeigt Leerzustand', async () => {
    h_.getRounds.mockResolvedValue({ success: true, data: { rounds: [] } })
    const { w } = await mountAt(BASE)
    expect(w.find('[data-testid="rounds-empty"]').text()).toBe('Noch keine Runden')
  })

  it('zeigt Fehler als Alarm und lädt erneut', async () => {
    h_.getRounds.mockRejectedValueOnce(new Error('kaputt'))
    const { w } = await mountAt(BASE)
    const err = w.find('[data-testid="rounds-error"]')
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('kaputt')
    await err.find('button').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="rounds-error"]').exists()).toBe(false)
    expect(w.find('[data-testid="round-1"]').exists()).toBe(true)
  })

  it('behandelt success=false als Fehler mit dem Backend-Text', async () => {
    h_.getRounds.mockResolvedValue({ success: false, error: 'Backend sagt nein' })
    const { w } = await mountAt(BASE)
    expect(w.find('[data-testid="rounds-error"]').text()).toContain('Backend sagt nein')
  })

  it('schaltet per Tastatur auf Aktionen und zurück, Zustand steht in der Query', async () => {
    const { w, router } = await mountAt(BASE)
    const radios = w.findAll('[role="radio"]')
    expect(radios.map((r) => r.attributes('aria-checked'))).toEqual(['true', 'false'])
    expect(radios.map((r) => r.attributes('tabindex'))).toEqual(['0', '-1'])
    await radios[0]!.trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBe('actions')
    expect(w.find('[data-testid="actions-panel"]').exists()).toBe(true)
    expect(w.find('[data-testid="rounds-list"]').exists()).toBe(false)
    await w.findAll('[role="radio"]')[1]!.trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBeUndefined()
    expect(w.find('[data-testid="rounds-list"]').exists()).toBe(true)
  })

  it('öffnet ?view=actions direkt, lädt Aktionen mit Filtern aus der Query und führt auf die Beitragsadresse', async () => {
    const { w, router } = await mountAt(`${BASE}?view=actions&round=1&platform=twitter&type=LIKE_POST`)
    expect(h_.getActions).toHaveBeenCalledWith(
      'sim_1',
      expect.objectContaining({ round_num: 1, platform: 'twitter', action_type: 'LIKE_POST' }),
    )
    await w.find('tr.sat-row--clickable').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunSimulationPost')
    expect(router.currentRoute.value.params.postId).toBe('twitter:post:42')
  })

  it('zeigt Fehler der Aktionen als Alarm', async () => {
    h_.getActions.mockRejectedValue(new Error('actions down'))
    const { w } = await mountAt(`${BASE}?view=actions`)
    const err = w.find('[data-testid="actions-error"]')
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('actions down')
  })

  it('ändert Filter in der Query und lädt neu', async () => {
    const { w, router } = await mountAt(`${BASE}?view=actions`)
    await w.find('[data-testid="filter-platform"]').setValue('reddit')
    await flushPromises()
    expect(router.currentRoute.value.query.platform).toBe('reddit')
    expect(router.currentRoute.value.query.view).toBe('actions')
    expect(h_.getActions).toHaveBeenLastCalledWith('sim_1', expect.objectContaining({ platform: 'reddit' }))
  })
})
