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

  it('Active-State: auf der Ablage mit Filter lauf ist genau "Läufe" aktiv und traegt aria-current', async () => {
    await router.push({ name: 'Shelf', query: { filter: 'lauf' } })
    await router.isReady()
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // „Läuft gerade“ und „Braucht dich“ teilen sich die Adresse, sind aber nie selbst aktiv.
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain('Läufe')
    expect(active[0]?.attributes('aria-current')).toBe('page')
  })

  it.each([
    { query: 'graph', label: 'Graphen' },
    { query: 'personasatz', label: 'Personasätze' },
    { query: 'jobs', label: 'Aktivität' },
  ])('Active-State: Ablage-Filter $query markiert "$label"', async ({ query, label }) => {
    await router.push({ name: 'Shelf', query: { filter: query } })
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain(label)
  })

  it('Active-State: ein geoeffneter Lauf (ShelfObject) markiert "Läufe"', async () => {
    await router.push({ name: 'ShelfObject', params: { kind: 'lauf', objectId: 'sim_1' } })
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const active = wrapper.findAll('.sidebar-item--active')
    expect(active).toHaveLength(1)
    expect(active[0]?.text()).toContain('Läufe')
  })

  it('Eintraege verlinken auf bestehende Adressen (Ablage-Filter, Vergleich-Fallback)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const hrefs = wrapper
      .findAll('a.sidebar-item')
      .map((a) => [a.text().replace(/\d+$/, '').trim(), a.attributes('href')])
    const byLabel = Object.fromEntries(hrefs)
    expect(byLabel['▶Läufe']).toBe('/ablage?filter=lauf')
    expect(byLabel['◇Graphen']).toBe('/ablage?filter=graph')
    expect(byLabel['◎Personasätze']).toBe('/ablage?filter=personasatz')
    expect(byLabel['◌Läuft gerade']).toBe('/ablage?filter=lauf')
    expect(byLabel['!Braucht dich']).toBe('/ablage?filter=lauf')
    expect(byLabel['≡Aktivität']).toBe('/ablage?filter=jobs')
    // Ohne bekannte Simulation: nächstliegende bestehende Adresse = Läufe-Liste.
    expect(byLabel['⇄Vergleich']).toBe('/ablage?filter=lauf')
    // System: die Seite, auf der der Systemzustand heute steht.
    expect(byLabel['System' + 'Alle Dienste erreichbar']).toBe('/dashboard')
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

  it('Settings-Sub-Items sichtbar wenn Settings-Group via localStorage offen', async () => {
    // Hydrate localStorage: settings-Group ist offen
    lsMock.setItem('agora.sidebar.v1', JSON.stringify({ settings: true }))
    // _resetForTesting nach dem localStorage-Setzen aufrufen, damit der
    // Singleton-State aus dem Mock-localStorage hydriert wird.
    useSidebarState._resetForTesting()
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    await wrapper.vm.$nextTick()
    const text = wrapper.text()
    // DE-Locale: general="Allgemein" — wire-Ziel laut IA-Matrix
    expect(text).toContain('Allgemein')
    // Fix #1713 (Befund 7): LLM-Routing und Audit-Logs sind jetzt Teil der
    // einen Einstellungen-Navigationsebene (vorher nur in SettingsOverlay,
    // eine zweite, parallele Navigation).
    expect(text).toContain('Audit-Logs')
    expect(text).toContain('LLM-Routing')
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
    it('zeigt die Einstellungen-Gruppe weiterhin, mit Provider-Keys vorne und Vorschau-Badges auf Betreiber-Punkten', async () => {
      lsMock.setItem('agora.sidebar.v1', JSON.stringify({ settings: true }))
      useSidebarState._resetForTesting()
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

      const text = wrapper.text()
      // Gruppe bleibt sichtbar — nur die eigenen Provider-Keys sind editierbar.
      expect(text).toContain('Einstellungen')
      expect(text).toContain('Provider-Keys')
      expect(text).toContain('Vorschau')

      const subItems = wrapper.findAll('.sidebar-sub-item')
      expect(subItems.length).toBeGreaterThan(0)
      expect(subItems[0]?.text()).toContain('Provider-Keys')
      // Provider-Keys selbst traegt kein Vorschau-Badge.
      expect(subItems[0]?.text()).not.toContain('Vorschau')
    })
  })

  describe('Deep-Link auf /workspace/provider-keys (#1688)', () => {
    it('oeffnet die geschlossene Einstellungen-Gruppe und zeigt Provider-Keys als aktives Ziel', async () => {
      // Kein localStorage-State: Gruppe waere ohne Route-Match geschlossen.
      const pinia = createPinia()
      setActivePinia(pinia)
      const auth = useAuthStore()
      auth.config = DEMO_CONFIG
      auth.session = { access_token: 'tok', user: { id: 'u1' } } as never

      await router.push({ name: 'WorkspaceProviderKeys' })
      const wrapper = mount(Sidebar, {
        global: { plugins: [router, pinia, i18n] },
      })
      await wrapper.vm.$nextTick()

      const subItems = wrapper.findAll('.sidebar-sub-item')
      expect(subItems.length).toBeGreaterThan(0)
      expect(subItems[0]?.text()).toContain('Provider-Keys')
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
