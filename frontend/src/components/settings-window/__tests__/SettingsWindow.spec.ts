/**
 * SettingsWindow — Etappe 3 (#1799), Ticket „Einstellungsfenster".
 *
 * Prueft: Abschnitt je Adresse, unbekannter Abschnitt → general, Schliessen
 * (zur vorherigen Adresse bzw. /library/runs), Zugangsregel je Abschnitt,
 * Liste mit aria-current, DOM-Reihenfolge = Sichtreihenfolge, Escape und
 * Fokus-Rueckkehr, Dialog-Beschriftung.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { useAuthStore } from '@/store/auth'
import { useSettingsWindowStore } from '@/stores/settingsWindow'
import type { AuthConfigResponse } from '@/contracts/authConfigContract'
import { SETTINGS_SECTIONS, SETTINGS_SECTION_IDS } from '../sections'

// Die beiden eingebetteten Altansichten sind gross und haengen an Stores/API;
// ihr Inhalt ist hier nicht Gegenstand.
vi.mock('@/views/Settings/SettingsGeneralView.vue', () => ({
  default: { name: 'GeneralViewStub', template: '<div data-testid="general-stub">Allgemein-Inhalt</div>' },
}))
vi.mock('@/views/Settings/EmbeddingConfigurationsView.vue', () => ({
  default: { name: 'EmbeddingViewStub', template: '<div data-testid="embedding-stub">Embedding-Inhalt</div>' },
}))

import SettingsWindow from '../SettingsWindow.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const SUPABASE_CONFIG: AuthConfigResponse = {
  auth_backend: 'supabase',
  jwt_enabled: true,
  supabase_url: null,
  supabase_anon_key: null,
  realtime_enabled: false,
  demo_mode: false,
}

const stub = { template: '<div />' }

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/library/runs', name: 'LibraryRuns', component: stub },
      { path: '/library/graphs', name: 'LibraryGraphs', component: stub },
      { path: '/settings/general', name: 'SettingsGeneral', component: stub, meta: { settingsWindow: true, settingsSection: 'general' } },
      { path: '/settings/embedding', name: 'SettingsEmbedding', component: stub, meta: { settingsWindow: true, settingsSection: 'embedding' } },
      { path: '/settings/:section', name: 'SettingsWindow', component: stub, meta: { settingsWindow: true } },
    ],
  })
}

let wrapper: VueWrapper | null = null

async function mountWindow(path: string, setup?: (pinia: ReturnType<typeof createPinia>) => void) {
  const pinia = createPinia()
  setActivePinia(pinia)
  setup?.(pinia)
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  wrapper = mount(SettingsWindow, { global: { plugins: [router, pinia, i18n] }, attachTo: document.body })
  await flushPromises()
  return { router, pinia }
}

function setVisitor(demo: boolean): void {
  const auth = useAuthStore()
  auth.config = { ...SUPABASE_CONFIG, demo_mode: demo }
  auth.session = { access_token: 'tok', user: { id: 'u1' } } as never
}

const q = <T extends Element>(sel: string) => document.body.querySelector<T>(sel)
const qa = <T extends Element>(sel: string) => Array.from(document.body.querySelectorAll<T>(sel))
const listLabels = () => qa('.sw__label').map((a) => a.textContent)

const LABEL_DE: Record<string, string> = {
  general: 'Allgemein',
  appearance: 'Aussehen',
  providers: 'Anbieter',
  profiles: 'Profile',
  embedding: 'Embedding',
  pipeline: 'Pipeline',
  budgets: 'Budgets',
  access: 'Zugang',
  system: 'System',
}

describe('SettingsWindow', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it.each(SETTINGS_SECTION_IDS)('öffnet auf /settings/%s den richtigen Abschnitt', async (id) => {
    await mountWindow(`/settings/${id}`)
    expect(q('.sw__heading')?.textContent).toBe(LABEL_DE[id])
    const current = qa('[aria-current="page"]')
    expect(current).toHaveLength(1)
    expect(current[0]?.getAttribute('data-testid')).toBe(`settings-section-${id}`)
    expect(current[0]?.textContent).toContain(LABEL_DE[id])
  })

  it('unbekannter Abschnitt → general', async () => {
    await mountWindow('/settings/gibt-es-nicht')
    expect(q('.sw__heading')?.textContent).toBe('Allgemein')
    expect(q('[aria-current="page"]')?.getAttribute('data-testid')).toBe('settings-section-general')
  })

  it('Allgemein und Embedding betten die bisherigen Ansichten unverändert ein', async () => {
    await mountWindow('/settings/general')
    expect(q('[data-testid="general-stub"]')).not.toBeNull()
    wrapper?.unmount()
    await mountWindow('/settings/embedding')
    expect(q('[data-testid="embedding-stub"]')).not.toBeNull()
  })

  it('die übrigen Abschnitte zeigen Überschrift und den Satz "kommt in dieser Etappe"', async () => {
    await mountWindow('/settings/budgets')
    expect(q('.sw__content')?.textContent).toContain('Dieser Abschnitt kommt in dieser Etappe.')
  })

  it('nur genau ein Eintrag der Liste trägt aria-current', async () => {
    await mountWindow('/settings/pipeline')
    expect(qa('.sw__item')).toHaveLength(9)
    expect(qa('.sw__item[aria-current]')).toHaveLength(1)
  })

  it('DOM-Reihenfolge ist die Sichtreihenfolge: Titel, Liste in Quell-Reihenfolge, dann Inhalt', async () => {
    await mountWindow('/settings/general')
    expect(listLabels()).toEqual(SETTINGS_SECTIONS.map((s) => LABEL_DE[s.id]))
    const title = q('.sw__title') as Element
    const firstItem = q('.sw__item') as Element
    const content = q('.sw__content') as Element
    expect(title.compareDocumentPosition(firstItem) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(firstItem.compareDocumentPosition(content) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('Dialog und Inhalt tragen aria-labelledby auf vorhandene Überschriften', async () => {
    await mountWindow('/settings/general')
    const dialog = q('[role="dialog"]') as HTMLElement
    const dialogTitle = document.getElementById(dialog.getAttribute('aria-labelledby') ?? '')
    expect(dialogTitle?.textContent).toBe('Einstellungen')
    const region = q('.sw__content') as HTMLElement
    const regionTitle = document.getElementById(region.getAttribute('aria-labelledby') ?? '')
    expect(regionTitle?.textContent).toBe('Allgemein')
  })

  describe('Schließen', () => {
    it('führt zur vorherigen Adresse', async () => {
      const { router, pinia } = await mountWindow('/settings/system', () => {
        useSettingsWindowStore().open('/library/graphs')
      })
      void pinia
      ;(q('.sw__close') as HTMLElement).click()
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/library/graphs')
    })

    it('führt bei Direktaufruf (nichts gemerkt) nach /library/runs', async () => {
      const { router } = await mountWindow('/settings/system')
      ;(q('.sw__close') as HTMLElement).click()
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/library/runs')
    })

    it('Esc schließt das Fenster', async () => {
      const { router } = await mountWindow('/settings/system', () => {
        useSettingsWindowStore().open('/library/graphs')
      })
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/library/graphs')
    })

    it('der Fokus kehrt zum Auslöser zurück', async () => {
      const opener = document.createElement('button')
      document.body.appendChild(opener)
      opener.focus()
      expect(document.activeElement).toBe(opener)
      await mountWindow('/settings/system')
      wrapper?.unmount()
      wrapper = null
      await flushPromises()
      await new Promise((r) => setTimeout(r, 10))
      expect(document.activeElement).toBe(opener)
    })
  })

  describe('Zugangsregel je Abschnitt', () => {
    it('Betreiber sieht alle neun Abschnitte, keiner ist gesperrt', async () => {
      await mountWindow('/settings/general')
      expect(qa('.sw__item')).toHaveLength(9)
      expect(q('.sw__locked')).toBeNull()
    })

    it('Besucher ohne Betreiber-Zugang (kein Demo) sieht nur offene Abschnitte', async () => {
      await mountWindow('/settings/appearance', () => setVisitor(false))
      const open = SETTINGS_SECTIONS.filter((s) => !s.operatorOnly).map((s) => LABEL_DE[s.id])
      expect(listLabels()).toEqual(open)
      expect(open).toEqual(['Aussehen', 'Anbieter', 'System'])
    })

    it('Besucher auf der Demo-Instanz sieht Betreiber-Abschnitte nur als gesperrte Vorschau', async () => {
      await mountWindow('/settings/pipeline', () => setVisitor(true))
      expect(qa('.sw__item')).toHaveLength(9)
      expect(q('.sw__locked')?.textContent).toContain('gehört dem Betreiber')
      expect(q('.sw__content')?.textContent).not.toContain('kommt in dieser Etappe')
    })

    it('die Regeln stehen in sections.ts: operatorOnly/requiresAuth je Abschnitt', () => {
      const rules = Object.fromEntries(
        SETTINGS_SECTIONS.map((s) => [s.id, [s.operatorOnly, s.requiresAuth]]),
      )
      expect(rules).toEqual({
        general: [true, false],
        appearance: [false, false],
        providers: [false, true],
        profiles: [true, true],
        embedding: [true, true],
        pipeline: [true, false],
        budgets: [true, false],
        access: [true, true],
        system: [false, false],
      })
    })
  })

  it('Abschnittswechsel über die Liste ersetzt den Verlaufseintrag (Zurück schließt das Fenster)', async () => {
    const { router } = await mountWindow('/settings/general')
    const before = router.options.history.state.position as number
    ;(q('[data-testid="settings-section-system"]') as HTMLElement).click()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/settings/system')
    expect(router.options.history.state.position).toBe(before)
  })
})
