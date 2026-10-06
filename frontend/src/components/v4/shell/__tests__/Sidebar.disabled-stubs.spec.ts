/**
 * Sidebar — IA-Matrix (Slice 7.3), aktualisiert durch Fix #1713 (Befund 7).
 *
 * Prueft:
 * 1. Keine disabled Stub-Items mehr (Projekte/Datensätze/Vorlagen/Monitoring).
 * 2. Keine Einstellungen-Sub-Items mehr (Etappe 3, #1799): eine Zeile
 *    „Einstellungen“ oeffnet das Einstellungsfenster, dessen Liste die
 *    Abschnitte traegt.
 * 3. Sidebar rendert weiterhin nur wire-Ziele laut Matrix.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { makeTestRouter } from './testRouter'
import { useSidebarState } from '@/composables/useSidebarState'
import Sidebar from '../Sidebar.vue'

vi.mock('@/composables/useLibraryCounts', async () => (await import('./sidebarMocks')).libraryCountsMock)
vi.mock('@/composables/useSidebarSystem', async () => (await import('./sidebarMocks')).sidebarSystemMock)

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
    for (const id of HIDDEN_NAV_IDS) expect(text).not.toContain(id)
  })

  // Etappe 3 (#1799): die Gruppe „Einstellungen“ mit Unterpunkten ist eine
  // Zeile; Audit-Logs/LLM-Routing stehen als Abschnitte im Einstellungsfenster
  // (Zugang bzw. Profile), nicht mehr in der Seitenleiste.
  it('zeigt keine Settings-Sub-Items mehr, auch wenn die Gruppe gespeichert offen war', async () => {
    lsMock.setItem('agora.sidebar.v1', JSON.stringify({ settings: true }))
    useSidebarState._resetForTesting()
    const wrapper = await mountSidebar()
    const text = wrapper.text()
    expect(text).not.toContain('Audit-Logs')
    expect(text).not.toContain('LLM-Routing')
    expect(wrapper.findAll('.sidebar-sub-item')).toHaveLength(0)
  })

  it('behaelt wire-Ziele: Läufe, Graphen, Personasätze, Aktivität sichtbar (#1795)', async () => {
    const wrapper = await mountSidebar()
    const text = wrapper.text()
    expect(text).toContain('Läufe')
    expect(text).toContain('Graphen')
    expect(text).toContain('Personasätze')
    expect(text).toContain('Aktivität')
  })
})