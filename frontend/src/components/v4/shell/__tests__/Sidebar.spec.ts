/**
 * Sidebar — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Rendert nav-Items.
 * 2. Active-State via Router (useLink in SidebarItem).
 * 3. Collapse-Click emittet collapse-toggle.
 * 4. Settings-Group oeffnet wenn localStorage-State gesetzt oder Route passt.
 *
 * Nach i18n-Migration (Slice 06): Labels kommen aus DE-Locale.
 * Nach Slice-2-Migration: active/subActive/settingsOpen Props entfernt.
 * State kommt aus useSidebarState (localStorage) + Router.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { makeTestRouter } from './testRouter'

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

// Zaehler und Systemzustand haben eigene Specs (useLibraryCounts.spec, Sidebar.counts.spec):
// hier laedt die Seitenleiste weder die Ablage noch /api/status.
vi.mock('@/composables/useLibraryCounts', async () => (await import('./sidebarMocks')).libraryCountsMock)
vi.mock('@/composables/useSidebarSystem', async () => (await import('./sidebarMocks')).sidebarSystemMock)

import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

// Lokale i18n-Instanz — kein Singleton-Import, um localStorage-Konflikte zu vermeiden
const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

import Sidebar from '../Sidebar.vue'
import { useSidebarState } from '@/composables/useSidebarState'
import { useAuthStore } from '@/store/auth'
import type { AuthConfigResponse } from '@/contracts/authConfigContract'

const SUPABASE_CONFIG: AuthConfigResponse = {
  auth_backend: 'supabase',
  jwt_enabled: true,
  supabase_url: null,
  supabase_anon_key: null,
  realtime_enabled: false,
  demo_mode: false,
}

const DEMO_CONFIG: AuthConfigResponse = {
  ...SUPABASE_CONFIG,
  demo_mode: true,
}

const router = makeTestRouter()

describe('Sidebar', () => {
  beforeEach(() => {
    lsMock.clear()
    useSidebarState._resetForTesting()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    // matchMedia via Object.defineProperty zurücksetzen falls gesetzt
    if (typeof window !== 'undefined' && (window as typeof window & { matchMedia?: unknown }).matchMedia) {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        configurable: true,
        value: undefined,
      })
    }
  })

  it('mountet ohne Crash', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert Brand-Wordmark "Agora"', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.text()).toContain('Agora')
  })

  it('rendert den Brand-Ring statt des blau-violetten Glyphen (Redesign PR 2)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // Kein <img>-Glyph mehr ...
    expect(wrapper.find('img[src*="agora-logo-glyph"]').exists()).toBe(false)
    // ... stattdessen der reine CSS-Ring aus AgoraBrand mode="ring".
    expect(wrapper.find('.agora-brand--ring').exists()).toBe(true)
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('rendert die Gliederung Bibliothek / Im Blick / Werkzeuge mit allen Eintraegen (#1795)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    for (const label of [
      'Bibliothek', 'Läufe', 'Graphen', 'Personasätze',
      'Im Blick', 'Läuft gerade', 'Braucht dich',
      'Werkzeuge', 'Vergleich', 'Aktivität',
      'System', 'Einstellungen',
    ]) {
      expect(text).toContain(label)
    }
    // Dashboard und Runs sind keine Eintraege mehr (ihre Adressen bleiben bestehen).
    expect(text).not.toContain('Dashboard')
    expect(text).not.toContain('Runs')
  })

  it('rendert Settings-Gruppe (DE: "Einstellungen")', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // DE-Locale: sidebar.settings.label = "Einstellungen"
    expect(wrapper.text()).toContain('Einstellungen')
  })

  it('Active-State: die Laeufe-Bibliothek markiert genau "Läufe" und traegt aria-current', async () => {
    await router.push({ name: 'LibraryRuns' })
    await router.isReady()
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // „Läuft gerade“ und „Braucht dich“ teilen sich den Pfad, sind aber nur mit ihrem `?view=` aktiv.
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain('Läufe')
    expect(active[0]?.attributes('aria-current')).toBe('page')
  })

  it.each([
    { view: 'running', label: 'Läuft gerade' },
    { view: 'attention', label: 'Braucht dich' },
  ])('Active-State: ?view=$view markiert "$label" und nicht "Läufe"', async ({ view, label }) => {
    await router.push({ name: 'LibraryRuns', query: { view } })
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain(label)
  })

  it('Active-State: ?view=with-report bleibt bei "Läufe"', async () => {
    await router.push({ name: 'LibraryRuns', query: { view: 'with-report' } })
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain('Läufe')
  })

  it.each([
    { path: '/library/graphs', label: 'Graphen' },
    { path: '/graphs/proj_1', label: 'Graphen' },
    { path: '/activity/jobs', label: 'Aktivität' },
    { path: '/activity/jobs/run_1', label: 'Aktivität' },
    { path: '/activity/log', label: 'Aktivität' },
    { path: '/compare/sim_1', label: 'Vergleich' },
    { path: '/simulations/sim_1', label: 'Läufe' },
    { path: '/library/runs/new', label: 'Läufe' },
  ])('Active-State: $path markiert "$label"', async ({ path, label }) => {
    await router.push(path)
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain(label)
  })

  it('Active-State: ein Lauf-Arbeitsbereich mit Kind-Route (RunWorkspace > RunGraph) markiert "Läufe"', async () => {
    const nested = makeTestRouter([
      {
        path: '/simulations/:simulationId',
        name: 'RunWorkspace',
        component: { template: '<div><router-view /></div>' },
        children: [{ path: 'graph', name: 'RunGraph', component: { template: '<div/>' } }],
      },
    ])
    await nested.push('/simulations/sim_1/graph')
    const wrapper = mount(Sidebar, {
      global: { plugins: [nested, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain('Läufe')
  })

  it('Active-State: die alte Objektansicht (ShelfObject) markiert nach Art', async () => {
    await router.push({ name: 'ShelfObject', params: { kind: 'bericht', objectId: 'report_1' } })
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain('Läufe')
  })

  it('Eintraege verlinken auf die Adressen der Etappe 2 (Vergleich ohne bekannte Simulation: /compare)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const hrefs = wrapper
      .findAll('a.sidebar-item')
      .map((a) => [a.text().replace(/\d+$/, '').trim(), a.attributes('href')])
    const byLabel = Object.fromEntries(hrefs)
    expect(byLabel['▶Läufe']).toBe('/library/runs')
    expect(byLabel['◇Graphen']).toBe('/library/graphs')
    // Personasätze haben bis Etappe 7 keine eigene Ansicht.
    expect(byLabel['◎Personasätze']).toBe('/library/runs')
    expect(byLabel['◌Läuft gerade']).toBe('/library/runs?view=running')
    expect(byLabel['!Braucht dich']).toBe('/library/runs?view=attention')
    expect(byLabel['≡Aktivität']).toBe('/activity/jobs')
    expect(byLabel['⇄Vergleich']).toBe('/compare')
    // System und Einstellungen oeffnen das Einstellungsfenster (Etappe 3, #1799).
    expect(byLabel['System' + 'Alle Dienste erreichbar']).toBe('/settings/system')
    expect(byLabel['Einstellungen']).toBe('/settings/general')
  })

  it('hat genau eine Zeile "Einstellungen" ohne Unterpunkte und Gruppe (#1799)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const rows = wrapper.findAll('a.sidebar-item').filter((a) => a.text() === 'Einstellungen')
    expect(rows).toHaveLength(1)
    expect(wrapper.find('.sidebar-group').exists()).toBe(false)
    expect(wrapper.findAll('.sidebar-sub-item')).toHaveLength(0)
  })

  it('die Zeile "Einstellungen" ist auf einer Fenster-Adresse aktiv und traegt aria-current (#1799)', async () => {
    await router.push('/settings/appearance')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const row = wrapper.findAll('a.sidebar-item').find((a) => a.text() === 'Einstellungen')
    expect(row?.attributes('aria-current')).toBe('page')
  })

  it('DOM-Reihenfolge der Seitenleiste entspricht der Sichtreihenfolge (Bauplan 3.1)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const labels = wrapper
      .findAll('a.sidebar-item')
      .map((a) => a.text().replace(/\d+$/, '').replace(/^[^\p{L}]+/u, '').trim())
      .slice(0, 9)
    // Danach (unten, mit Abstand): System, dann Einstellungen.
    expect(labels).toEqual([
      'Läufe', 'Graphen', 'Personasätze', 'Läuft gerade', 'Braucht dich', 'Vergleich', 'Aktivität',
      'SystemAlle Dienste erreichbar', 'Einstellungen',
    ])
  })

  it('zeigt die Zaehler neutral neben den Eintraegen und haengt sie in den zugaenglichen Namen', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const counts = wrapper.findAll('.sidebar-item__count').map((c) => c.text())
    // Bibliothek 9/3/2, Im Blick 0/2, Aktivität 42 (Stub); Vergleich hat keinen Zaehler.
    expect(counts).toEqual(['9', '3', '2', '0', '2', '42'])
  })

  it('eingeklappt: nur Symbole, aber zugaengliche Namen mit Zaehler und kein Gruppentitel', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { collapsed: true },
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.find('.sidebar__group-title').exists()).toBe(false)
    expect(wrapper.find('.sidebar-item__label').exists()).toBe(false)
    const runs = wrapper.findAll('a.sidebar-item').find((a) => a.attributes('aria-label')?.startsWith('Läufe'))
    expect(runs?.attributes('aria-label')).toBe('Läufe, 9')
    expect(runs?.attributes('title')).toBe('Läufe, 9')
    const system = wrapper.findAll('a.sidebar-item').find((a) => a.attributes('aria-label')?.startsWith('System'))
    expect(system?.attributes('aria-label')).toBe('System: Alle Dienste erreichbar')
    // Einstellungen: ein Symbol zur ersten Einstellungsseite statt der Gruppe.
    expect(wrapper.find('.sidebar-group').exists()).toBe(false)
  })

  it('kein active-Item wenn Route "/" (redirect, kein Exact-Match auf Item)', async () => {
    // "/" redirected zu Dashboard — nach isReady ist aktuelle Route /dashboard
    // also erwarten wir ggf. einen aktiven Item; wir pruefen nur dass kein Crash
    await router.push('/')
    await router.isReady()
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // Kein Crash — Komponente muss existieren
    expect(wrapper.exists()).toBe(true)
  })

  it('Collapse-Footer-Click emittet collapse-toggle', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    await wrapper.find('.sidebar__footer').trigger('click')
    expect(wrapper.emitted('collapse-toggle')).toBeTruthy()
  })

  it('Collapse-Footer ist ein echtes <button> mit zugaenglichem Namen (Slice 7.3.2 a11y)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { collapsed: false },
      global: { plugins: [router, i18n] },
    })
    const footer = wrapper.find('.sidebar__footer')
    expect(footer.element.tagName).toBe('BUTTON')
    expect(footer.attributes('type')).toBe('button')
    expect(footer.attributes('aria-label')).toBe('Einklappen')
  })

  it('Collapse-Footer traegt aria-label "Ausklappen" im eingeklappten Zustand (Slice 7.3.2 a11y)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { collapsed: true },
      global: { plugins: [router, i18n] },
    })
    const footer = wrapper.find('.sidebar__footer')
    expect(footer.attributes('aria-label')).toBe('Ausklappen')
  })

  it('Collapse-Footer per Enter/Leertaste bedienbar (Slice 7.3.2 a11y)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const footer = wrapper.find('.sidebar__footer')
    // Native <button>-Semantik: Enter/Space loesen 'click' aus (Browser-Default,
    // kein manueller Handler noetig) — hier wird das Click-Event simuliert,
    // das der Browser bei Enter/Space fuer <button> nativ ausloest.
    await footer.trigger('click')
    expect(wrapper.emitted('collapse-toggle')).toBeTruthy()
  })

  it('zeigt auch mit gespeichertem "Gruppe offen" keine Einstellungs-Unterpunkte mehr (#1799)', async () => {
    // Alter localStorage-Stand der Gruppe darf nichts wieder aufklappen.
    lsMock.setItem('agora.sidebar.v1', JSON.stringify({ settings: true }))
    useSidebarState._resetForTesting()
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    await wrapper.vm.$nextTick()
    const text = wrapper.text()
    // Die Abschnitte stehen in der Liste des Fensters, nicht in der Seitenleiste.
    expect(text).not.toContain('Allgemein')
    expect(text).not.toContain('Audit-Logs')
    expect(text).not.toContain('LLM-Routing')
  })

  // Slice 7.3.2: Breakpoint-Vereinheitlichung — Mobile = "< 768px" (SSoT:
  // src/constants/breakpoints.ts). Bei genau 768px gilt bereits Desktop, konsistent
  // mit AppShell.vue's Resize-Handler (window.innerWidth >= 768).
  it.each([
    { width: 767, expectMobile: true },
    { width: 768, expectMobile: false },
    { width: 769, expectMobile: false },
  ])(
    'handleNavClick bei $width px: expectMobile=$expectMobile (matchMedia < 768, Slice 7.3.2)',
    async ({ width, expectMobile }) => {
      await router.push('/')
      const pinia = createPinia()
      setActivePinia(pinia)

      // matchMedia-Mock via Object.defineProperty: jsdom unterstuetzt matchMedia nicht nativ.
      // Simuliert den realen Browser-Vergleich fuer die Query "(max-width: 767px)".
      const matchMediaMock = vi.fn((query: string) => {
        const m = /max-width:\s*(\d+)px/.exec(query)
        const maxWidth = m ? Number(m[1]) : Infinity
        return {
          matches: width <= maxWidth,
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        }
      })
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        configurable: true,
        value: matchMediaMock,
      })

      const { useShellStore } = await import('@/stores/shell')
      const store = useShellStore()
      store.openMobileNav()

      const wrapper = mount(Sidebar, {
        global: { plugins: [router, pinia, i18n] },
      })
      await wrapper.vm.$nextTick()

      // handleNavClick direkt aufrufen (entspricht Nav-Item-Click im Drawer).
      // SidebarItem mit `to`-Prop emittiert kein 'click'-Event in Vue 3 (RouterLink handelt),
      // daher vm-direkter Aufruf — testet die matchMedia-Logik isoliert.
      const vm = wrapper.vm as unknown as { handleNavClick: () => void }
      vm.handleNavClick()
      await wrapper.vm.$nextTick()

      // Mobile (< 768px): handleNavClick schliesst den Drawer → mobileNavOpen=false.
      // Desktop (>= 768px): handleNavClick ist ein No-Op → mobileNavOpen bleibt true.
      expect(store.mobileNavOpen).toBe(!expectMobile)
      // Sicherstellen dass matchMedia mit dem korrekten (SSoT-)Breakpoint-Query aufgerufen wurde
      expect(matchMediaMock).toHaveBeenCalledWith('(max-width: 767px)')
    },
  )

  it('Settings-Sub-Items ausgeblendet wenn Settings-Group geschlossen (kein localStorage-State)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    expect(text).not.toContain('Allgemein')
  })

  it('Navigation-Element traegt eindeutigen aria-label (Sidebar-A11y-Gate)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const nav = wrapper.find('nav.sidebar__body')
    expect(nav.exists()).toBe(true)
    expect(nav.attributes('aria-label')).toBe('Hauptnavigation')
  })

  describe('Besucher ohne Betreiber-Zugang auf der Demo-Instanz (demo_mode:true, #1697)', () => {
    it('zeigt die Zeile "Einstellungen" weiterhin, ohne Unterpunkte und ohne Vorschau-Badges', async () => {
      const pinia = createPinia()
      setActivePinia(pinia)
      const auth = useAuthStore()
      auth.config = DEMO_CONFIG
      auth.session = { access_token: 'tok', user: { id: 'u1' } } as never

      await router.push('/')
      const wrapper = mount(Sidebar, {
        global: { plugins: [router, pinia, i18n] },
      })
      await wrapper.vm.$nextTick()

      // Zeile bleibt sichtbar; Vorschau/Sperre der Betreiber-Abschnitte zeigt das Fenster.
      expect(wrapper.text()).toContain('Einstellungen')
      expect(wrapper.findAll('.sidebar-sub-item')).toHaveLength(0)
      expect(wrapper.text()).not.toContain('Vorschau')
    })
  })

  describe('Deep-Link aus dem Demo-Vorschau-Banner auf /settings/providers (#1688)', () => {
    it('markiert die Zeile "Einstellungen" als aktiv (Fenster-Abschnitt Anbieter)', async () => {
      const pinia = createPinia()
      setActivePinia(pinia)
      const auth = useAuthStore()
      auth.config = DEMO_CONFIG
      auth.session = { access_token: 'tok', user: { id: 'u1' } } as never

      await router.push({ name: 'SettingsWindow', params: { section: 'providers' } })
      const wrapper = mount(Sidebar, {
        global: { plugins: [router, pinia, i18n] },
      })
      await wrapper.vm.$nextTick()

      const row = wrapper.findAll('a.sidebar-item').find((a) => a.text() === 'Einstellungen')
      expect(row?.attributes('aria-current')).toBe('page')
    })
  })

  describe('Besucher ohne Betreiber-Zugang OHNE Demo-Modus (regulaerer JWT-Mandant, #1697)', () => {
    it('blendet die Einstellungen-Gruppe komplett aus — kein Vorschau-Badge, keine Provider-Keys-Verknuepfung', async () => {
      lsMock.setItem('agora.sidebar.v1', JSON.stringify({ settings: true }))
      useSidebarState._resetForTesting()
      const pinia = createPinia()
      setActivePinia(pinia)
      const auth = useAuthStore()
      auth.config = SUPABASE_CONFIG
      auth.session = { access_token: 'tok', user: { id: 'u1' } } as never

      await router.push('/')
      const wrapper = mount(Sidebar, {
        global: { plugins: [router, pinia, i18n] },
      })
      await wrapper.vm.$nextTick()

      expect(wrapper.text()).not.toContain('Einstellungen')
      expect(wrapper.text()).not.toContain('Provider-Keys')
      expect(wrapper.text()).not.toContain('Vorschau')
      expect(wrapper.findAll('.sidebar-sub-item')).toHaveLength(0)
    })
  })
})
