/**
 * CompareView — Smoke-Tests (Slice I, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. PageHeader rendert title="Compare".
 * 3. BranchComparePanel wird eingebunden.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

// localStorage-Mock (benoetigt von useShellStore)
const lsMock = (() => {
  const s: Record<string, string> = {}
  return {
    getItem: (k: string) => s[k] ?? null,
    setItem: (k: string, v: string) => { s[k] = v },
    removeItem: (k: string) => { delete s[k] },
    clear: () => { Object.keys(s).forEach((k) => { delete s[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: lsMock, writable: true })

// BranchComparePanel hat interne API-Calls — per vi.mock stubben
vi.mock('@/components/compare/BranchComparePanel.vue', () => ({
  default: {
    name: 'BranchComparePanel',
    props: ['simulationId', 'availableBranches'],
    template: '<div data-testid="branch-compare-panel" />',
  },
}))

// listSimulationBranches mocken damit kein echter Fetch passiert.
// WICHTIG: in der Envelope-Form, die der Interceptor tatsaechlich
// liefert. Der frueher hier gemockte nackte Array liess den Test gruen
// laufen, waehrend die Ansicht in Wahrheit bei jedem Aufruf in den
// catch-Zweig fiel und „Fehler beim Laden der Branches" zeigte.
vi.mock('@/api/simulation', () => ({
  listSimulationBranches: vi.fn().mockResolvedValue({ success: true, data: [] }),
}))

import { listSimulationBranches } from '@/api/simulation'
import CompareView from '../CompareView.vue'

const stubComponent = { template: '<div/>' }
const router = makeTestRouter([
  { path: '/v4/compare/:simulationId', name: 'CompareV4', component: stubComponent, props: true },
])

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: { views: { compare: { title: 'Compare' } } }, en: {} } })

describe('CompareView (v4)', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
  })

  it('mountet ohne Crash', async () => {
    await router.push('/v4/compare/sim-001')
    const wrapper = mount(CompareView, {
      props: { simulationId: 'sim-001' },
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('PageHeader rendert title "Compare"', async () => {
    await router.push('/v4/compare/sim-001')
    const wrapper = mount(CompareView, {
      props: { simulationId: 'sim-001' },
      global: { plugins: [router, createPinia(), i18n] },
    })
    const title = wrapper.find('.page-header__title')
    expect(title.exists()).toBe(true)
    expect(title.text()).toBe('Compare')
  })

  it('liest die Branches aus der Envelope und nutzt simulation_id als Kennung', async () => {
    vi.mocked(listSimulationBranches).mockResolvedValueOnce({
      success: true,
      data: [
        { simulation_id: 'sim-branch-1', branch_name: 'Variante A', status: 'completed' },
        { simulation_id: 'sim-branch-2', branch_name: null, status: 'completed' },
      ],
    } as never)

    await router.push('/v4/compare/sim-001')
    const wrapper = mount(CompareView, {
      props: { simulationId: 'sim-001' },
      global: { plugins: [router, createPinia(), i18n] },
    })
    await flushPromises()

    // Geprueft wird die Prop, nicht das gerenderte Markup: kaputt war
    // das Auspacken der Envelope, nicht die Darstellung im Kind.
    const panel = wrapper.findComponent({ name: 'BranchComparePanel' })
    expect(panel.exists()).toBe(true)
    expect(panel.props('availableBranches')).toEqual([
      { id: 'sim-branch-1', label: 'Variante A', completed_at: undefined },
      // Ohne Branch-Name faellt die Beschriftung auf die ID zurueck.
      { id: 'sim-branch-2', label: 'sim-branch-2', completed_at: undefined },
    ])
  })

  it('BranchComparePanel wird nach Branch-Load gerendert', async () => {
    await router.push('/v4/compare/sim-001')
    const wrapper = mount(CompareView, {
      props: { simulationId: 'sim-001' },
      global: { plugins: [router, createPinia(), i18n] },
    })
    // onMounted ist async — flushPromises abwarten
    const { flushPromises } = await import('@vue/test-utils')
    await flushPromises()
    expect(wrapper.find('[data-testid="branch-compare-panel"]').exists()).toBe(true)
  })
})
