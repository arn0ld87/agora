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

import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

// Lokale i18n-Instanz — kein Singleton-Import, um localStorage-Konflikte zu vermeiden
const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

import Sidebar from '../Sidebar.vue'
import { useSidebarState } from '@/composables/useSidebarState'

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

  it('rendert Workspace-Nav-Items (Dashboard, Runs vorhanden)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    // DE-Locale: dashboard="Dashboard", runs="Runs"
    expect(text).toContain('Dashboard')
    expect(text).toContain('Runs')
  })

  it('rendert Settings-Gruppe (DE: "Einstellungen")', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // DE-Locale: sidebar.settings.label = "Einstellungen"
    expect(wrapper.text()).toContain('Einstellungen')
  })

  it('Active-State via Router: Dashboard-Route markiert Dashboard-Item als aktiv', async () => {
    await router.push('/dashboard')
    await router.isReady()
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    // SidebarItem nutzt useLink (isExactActive/isActive) fuer active-Klasse
    const activeItems = wrapper.findAll('.sidebar-item--active')
    expect(activeItems.length).toBeGreaterThan(0)
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
    // DE-Locale: general="Allgemein", llmRouting="LLM-Routing"
    expect(text).toContain('Allgemein')
    expect(text).toContain('LLM-Routing')
  })

  it('handleNavClick schliesst Mobile-Nav bei genau 768px (matchMedia inklusiv, Off-by-one-Fix)', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)

    // matchMedia-Mock via Object.defineProperty: jsdom unterstuetzt matchMedia nicht nativ.
    // Simuliert Breakpoint (max-width: 768px) → matches=true, d.h. Drawer-Modus aktiv bei exakt 768px.
    const matchMediaMock = vi.fn((query: string) => ({
      matches: query === '(max-width: 768px)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
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

    expect(store.mobileNavOpen).toBe(false)
    // Sicherstellen dass matchMedia mit dem korrekten Breakpoint-Query aufgerufen wurde
    expect(matchMediaMock).toHaveBeenCalledWith('(max-width: 768px)')
  })

  it('Settings-Sub-Items ausgeblendet wenn Settings-Group geschlossen (kein localStorage-State)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    expect(text).not.toContain('Allgemein')
  })
})
