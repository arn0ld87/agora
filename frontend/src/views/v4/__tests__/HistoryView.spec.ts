/**
 * HistoryView — Smoke-Tests (Slice I, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. PageHeader rendert title="Verlauf" + subtitle.
 * 3. HistoryDatabase wird eingebunden.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
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

// HistoryDatabase hat interne API-Calls — per vi.mock stubben
vi.mock('@/components/HistoryDatabase.vue', () => ({
  default: {
    name: 'HistoryDatabase',
    template: '<div data-testid="history-database" />',
  },
}))

import HistoryView from '../HistoryView.vue'

const stubComponent = { template: '<div/>' }
const router = makeTestRouter([
  { path: '/v4/history', name: 'HistoryV4', component: stubComponent },
])

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: {}, en: {} } })

describe('HistoryView (v4)', () => {
  // Still async console-output (Vue/jdom warnings) during jsdom environment
  // teardown. Without this, a pending console callback at worker-rpc close can
  // trigger a flaky "EnvironmentTeardownError: Closing rpc while onUserConsoleLog
  // was pending" race in the full suite. Test assertions are unaffected.
  let consoleSpies: Array<ReturnType<typeof vi.spyOn>> = []

  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
    consoleSpies = [
      vi.spyOn(console, 'warn').mockImplementation(() => {}),
      vi.spyOn(console, 'error').mockImplementation(() => {}),
    ]
  })

  afterEach(() => {
    consoleSpies.forEach((s) => s.mockRestore())
    consoleSpies = []
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
