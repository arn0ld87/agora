/**
 * AppShell — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. Sidebar-Slot wird gerendert.
 * 3. Topbar-Slot wird gerendert.
 * 4. Default-Main-Slot wird gerendert.
 * 5. Inspector-Slot ist default geschlossen.
 * 6. Backdrop wird gerendert wenn mobileNavOpen=true.
 * 7. Click auf Backdrop schliesst Mobile-Nav.
 * 8. ESC schliesst Mobile-Nav.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from './testRouter'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

// Lokale i18n-Instanz — kein Singleton-Import, um localStorage-Konflikte zu vermeiden
const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

// localStorage-Mock
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

import AppShell from '../AppShell.vue'

const router = makeTestRouter()

describe('AppShell', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.body.style.overflow = ''
  })

  it('mountet ohne Crash', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert Standard-Sidebar-Slot (Sidebar-Komponente)', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    // Sidebar hat class app-shell__sidebar
    expect(wrapper.find('.app-shell__sidebar').exists()).toBe(true)
  })

  it('rendert Topbar-Slot', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.find('.app-shell__topbar').exists()).toBe(true)
  })

  it('rendert benannten Sidebar-Slot-Inhalt', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      slots: {
        sidebar: '<div class="custom-sidebar">Sidebar</div>',
      },
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.find('.custom-sidebar').exists()).toBe(true)
  })

  it('rendert Main-Default-Slot-Inhalt', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      slots: {
        default: '<div class="main-content">Main</div>',
      },
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.find('.main-content').exists()).toBe(true)
  })

  it('Inspector-Slot ist default geschlossen', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia(), i18n] },
    })
    expect(wrapper.find('.app-shell__inspector').exists()).toBe(false)
  })

  it('Inspector-Slot wird sichtbar wenn inspectorOpen=true im Store', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      slots: {
        inspector: '<div class="inspector-content">Inspector</div>',
      },
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openInspector()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.app-shell__inspector').exists()).toBe(true)
    expect(wrapper.find('.inspector-content').exists()).toBe(true)
  })

  it('Backdrop wird gerendert wenn mobileNavOpen=true', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()

    // Kein Backdrop initial
    expect(wrapper.find('.app-shell__backdrop').exists()).toBe(false)

    store.openMobileNav()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.app-shell__backdrop').exists()).toBe(true)
  })

  it('Click auf Backdrop schliesst Mobile-Nav', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openMobileNav()
    await wrapper.vm.$nextTick()

    await wrapper.find('.app-shell__backdrop').trigger('click')

    expect(store.mobileNavOpen).toBe(false)
  })

  it('Resize auf Desktop-Breite schliesst Mobile-Nav und entfernt Scroll-Lock', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()

    // Drawer öffnen — Scroll-Lock wird gesetzt
    store.openMobileNav()
    await nextTick()
    expect(store.mobileNavOpen).toBe(true)
    expect(document.body.style.overflow).toBe('hidden')

    // Fenster auf Desktop-Breite resizen
    vi.stubGlobal('innerWidth', 1024)
    window.dispatchEvent(new Event('resize'))
    await nextTick()

    expect(store.mobileNavOpen).toBe(false)
    // Watcher reagiert auf mobileNavOpen=false → overflow wieder leer
    expect(document.body.style.overflow).toBe('')
  })

  it('ESC schliesst Mobile-Nav', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openMobileNav()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(store.mobileNavOpen).toBe(false)
  })
})
