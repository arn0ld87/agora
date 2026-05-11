/**
 * CompareView — Smoke-Tests (Slice I, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. PageHeader rendert title="Compare".
 * 3. BranchComparePanel wird eingebunden.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'

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

// listSimulationBranches mocken damit kein echter Fetch passiert
vi.mock('@/api/simulation', () => ({
  listSimulationBranches: vi.fn().mockResolvedValue([]),
}))

import CompareView from '../CompareView.vue'

const stubComponent = { template: '<div/>' }
// Sidebar referenziert Runs + Settings — beide muessen im Test-Router stehen
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'Home', component: stubComponent },
    { path: '/runs', name: 'Runs', component: stubComponent },
    { path: '/settings', name: 'Settings', component: stubComponent },
    { path: '/v4/compare/:simulationId', name: 'CompareV4', component: stubComponent, props: true },
  ],
})

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: {}, en: {} } })

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
