import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

import de from '../../../i18n/locales/de.json'
import en from '../../../i18n/locales/en.json'

// Composables stubben — wir testen die View-Orchestrierung, nicht die Polling-Logik
vi.mock('@/composables/useRunsPolling', () => ({
  useRunsPolling: () => ({
    runs: ref([]),
    loading: ref(false),
    error: ref(''),
    isRunning: ref(true),
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/composables/useSystemStatus', () => ({
  useSystemStatus: () => ({
    status: ref(null),
    loading: ref(false),
    error: ref(''),
    isRunning: ref(true),
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined),
  }),
}))

// Sub-Komponenten zu data-testid-Stubs reduzieren
vi.mock('@/components/v4/dashboard/HeroNewRun.vue', () => ({
  default: { name: 'HeroNewRun', template: '<section data-testid="hero-new-run" />' },
}))
vi.mock('@/components/v4/dashboard/StatsRow.vue', () => ({
  default: { name: 'StatsRow', template: '<section data-testid="stats-row" />' },
}))
vi.mock('@/components/v4/dashboard/ActiveRunsCard.vue', () => ({
  default: { name: 'ActiveRunsCard', template: '<section data-testid="active-runs-card" />' },
}))
vi.mock('@/components/v4/dashboard/SystemHealthCard.vue', () => ({
  default: { name: 'SystemHealthCard', template: '<section data-testid="system-health-card" />' },
}))
vi.mock('@/components/v4/dashboard/RecentReportsCard.vue', () => ({
  default: { name: 'RecentReportsCard', template: '<section data-testid="recent-reports-card" />' },
}))
vi.mock('@/components/v4/dashboard/QuickActionsRow.vue', () => ({
  default: { name: 'QuickActionsRow', template: '<section data-testid="quick-actions-row" />' },
}))

import DashboardView from '../DashboardView.vue'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

describe('DashboardView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('rendert Breadcrumb Dashboard', async () => {
    const router = makeTestRouter()
    await router.push('/dashboard')
    const wrapper = mount(DashboardView, {
      global: { plugins: [router, createPinia(), makeI18n()] },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Dashboard')
  })

  it('rendert alle Dashboard-Sections', async () => {
    const router = makeTestRouter()
    await router.push('/dashboard')
    const wrapper = mount(DashboardView, {
      global: { plugins: [router, createPinia(), makeI18n()] },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="hero-new-run"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-row"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="active-runs-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="system-health-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recent-reports-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="quick-actions-row"]').exists()).toBe(true)
  })
})
