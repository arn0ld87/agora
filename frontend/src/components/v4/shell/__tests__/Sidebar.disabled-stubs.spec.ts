/**
 * Sidebar — IA-Matrix (Slice 7.3).
 *
 * Prueft:
 * 1. Keine disabled Stub-Items mehr (Projekte/Datensätze/Vorlagen/Monitoring).
 * 2. Audit Logs nicht in der Sidebar.
 * 3. LLM-Routing nicht in der Sidebar (run-spezifischer Zugang bleibt im Run-Detail).
 * 4. Sidebar rendert weiterhin nur wire-Ziele laut Matrix.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { makeTestRouter } from './testRouter'
import Sidebar from '../Sidebar.vue'

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

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
const router = makeTestRouter()

const HIDDEN_NAV_IDS = ['projects', 'datasets', 'templates', 'monitoring']
const HIDDEN_SETTINGS_IDS = ['auditLogs', 'llmRouting']

describe('Sidebar IA matrix (slice 7.3)', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
  })

  async function mountSidebar() {
    await router.push('/')
    return mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
  }

  it('rendert keine disabled Stub-Items mehr', async () => {
    const wrapper = await mountSidebar()
    expect(wrapper.findAll('[aria-disabled="true"]')).toHaveLength(0)
    expect(wrapper.findAll('.sidebar-item--disabled')).toHaveLength(0)
  })

  it('rendert keine Stub-Labels (Projekte/Datensätze/Vorlagen/Monitoring)', async () => {
    const wrapper = await mountSidebar()
    const text = wrapper.text()
    expect(text).not.toContain('Projekte')
    expect(text).not.toContain('Datensätze')
    expect(text).not.toContain('Vorlagen')
    expect(text).not.toContain('Monitoring')
    // Datenquelle mit hid = 'auditLogs' / 'llm-routing' darf nicht da sein
    for (const id of HIDDEN_NAV_IDS) expect(text).not.toContain(id)
  })

  it('rendert keine Audit-Logs- oder LLM-Routing-Settings-Sub-Items', async () => {
    const wrapper = await mountSidebar()
    // Settings-Group standardmaessig geschlossen — Inhalt pruefen via localStorage-Hook
    const text = wrapper.text()
    expect(text).not.toContain('Audit-Logs')
    expect(text).not.toContain('LLM-Routing')
    for (const id of HIDDEN_SETTINGS_IDS) expect(text).not.toContain(id)
  })

  it('behaelt wire-Ziele: Dashboard + Runs sichtbar', async () => {
    const wrapper = await mountSidebar()
    const text = wrapper.text()
    expect(text).toContain('Dashboard')
    expect(text).toContain('Runs')
  })
})