/**
 * HistoryView — Smoke-Tests (Slice I, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. PageHeader rendert title="Verlauf" + subtitle.
 * 3. HistoryDatabase wird eingebunden.
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

// HistoryDatabase hat interne API-Calls — per vi.mock stubben
vi.mock('@/components/HistoryDatabase.vue', () => ({
  default: {
    name: 'HistoryDatabase',
    template: '<div data-testid="history-database" />',
  },
}))

import HistoryView from '../HistoryView.vue'

const stubComponent = { template: '<div/>' }
// Sidebar referenziert Runs + Settings — beide muessen im Test-Router stehen
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'Home', component: stubComponent },
    { path: '/runs', name: 'Runs', component: stubComponent },
    { path: '/settings', name: 'Settings', component: stubComponent },
    { path: '/v4/history', name: 'HistoryV4', component: stubComponent },
  ],
})

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: {}, en: {} } })

describe('HistoryView (v4)', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
  })

  it('mountet ohne Crash', async () => {
    await router.push('/v4/history')
    const wrapper = mount(HistoryView, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('PageHeader rendert title "Verlauf"', async () => {
    await router.push('/v4/history')
    const wrapper = mount(HistoryView, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    const title = wrapper.find('.page-header__title')
    expect(title.exists()).toBe(true)
    expect(title.text()).toBe('Verlauf')
  })

  it('PageHeader rendert subtitle', async () => {
    await router.push('/v4/history')
    const wrapper = mount(HistoryView, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    const subtitle = wrapper.find('.page-header__subtitle')
    expect(subtitle.exists()).toBe(true)
    expect(subtitle.text()).toBe('Run- und Branch-Historie')
  })

  it('HistoryDatabase wird gerendert', async () => {
    await router.push('/v4/history')
    const wrapper = mount(HistoryView, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.find('[data-testid="history-database"]').exists()).toBe(true)
  })
})
