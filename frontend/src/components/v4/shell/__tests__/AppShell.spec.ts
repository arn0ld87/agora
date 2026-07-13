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
import { useCommandPalette } from '@/composables/useCommandPalette'
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
const commandPaletteStub = { template: '<div data-testid="command-palette" />' }

describe('AppShell', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
    useCommandPalette().close()
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

  it('behält die Command-Palette nach dem ersten Öffnen gemountet', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: {
        plugins: [router, createPinia(), i18n],
        stubs: { CommandPalette: commandPaletteStub },
      },
    })
    const palette = useCommandPalette()

    expect(wrapper.find('[data-testid="command-palette"]').exists()).toBe(false)

    palette.open()
    await nextTick()
    expect(wrapper.find('[data-testid="command-palette"]').exists()).toBe(true)

    palette.close()
    await nextTick()
    expect(wrapper.find('[data-testid="command-palette"]').exists()).toBe(true)
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

  // Slice 7.3.2: Breakpoint-Vereinheitlichung — Mobile = "< 768px" (SSoT:
  // src/constants/breakpoints.ts). onResize schliesst den Drawer nur bei
  // window.innerWidth >= 768 (Desktop). Bei 767px bleibt der Drawer offen.
  it.each([
    { width: 767, expectClosed: false },
    { width: 768, expectClosed: true },
    { width: 769, expectClosed: true },
  ])('Resize auf $width px: Drawer bleibt/schliesst konsistent mit MOBILE_BREAKPOINT_PX', async ({ width, expectClosed }) => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openMobileNav()
    await nextTick()

    vi.stubGlobal('innerWidth', width)
    window.dispatchEvent(new Event('resize'))
    await nextTick()

    expect(store.mobileNavOpen).toBe(!expectClosed)
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

  it('Mobile-Drawer traegt role=dialog + aria-modal=true + aria-label wenn offen (Slice 7.3 a11y)', async () => {
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

    const drawer = wrapper.find('[data-app-shell-drawer]')
    expect(drawer.exists()).toBe(true)
    expect(drawer.attributes('role')).toBe('dialog')
    expect(drawer.attributes('aria-modal')).toBe('true')
    expect(drawer.attributes('aria-label')).toBeTruthy()
  })

  it('Fokus kehrt zum Trigger (Hamburger) zurueck wenn der Drawer per Backdrop geschlossen wird (Slice 7.3 a11y)', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()

    // Hamburger (Topbar-Trigger) simuliert als Opener-Element
    const opener = document.createElement('button')
    opener.id = 'fake-hamburger'
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)

    // Drawer oeffnen — AppShell soll Fokus in den Drawer verschieben
    store.openMobileNav()
    await wrapper.vm.$nextTick()
    await nextTick()
    const focusedAfterOpen = document.activeElement
    expect(focusedAfterOpen).not.toBe(opener)
    // Fokus liegt innerhalb des Drawers
    const drawer = wrapper.find('[data-app-shell-drawer]')
    expect(drawer.element.contains(focusedAfterOpen)).toBe(true)

    // Drawer schliessen — Fokus springt zurueck zum Opener
    await wrapper.find('.app-shell__backdrop').trigger('click')
    await nextTick()
    expect(store.mobileNavOpen).toBe(false)
    expect(document.activeElement).toBe(opener)

    document.body.removeChild(opener)
    wrapper.unmount()
  })

  it('Main und Topbar sind inert waehrend der Drawer offen ist (Slice 7.3.2 Focus-Trap)', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()

    // Geschlossen: weder Main noch Topbar sind inert
    expect(wrapper.find('.app-shell__main').attributes('inert')).toBeUndefined()
    expect(wrapper.find('.app-shell__topbar').attributes('inert')).toBeUndefined()

    store.openMobileNav()
    await nextTick()

    // jsdom's inert-Reflektion ist kein 1:1-Abbild des Browser-Verhaltens
    // (Attribut-Wert statt leerem String) — geprueft wird daher nur Praesenz.
    expect(wrapper.find('.app-shell__main').attributes('inert')).toBeDefined()
    expect(wrapper.find('.app-shell__topbar').attributes('inert')).toBeDefined()

    store.closeMobileNav()
    await nextTick()

    expect(wrapper.find('.app-shell__main').attributes('inert')).toBeUndefined()
    expect(wrapper.find('.app-shell__topbar').attributes('inert')).toBeUndefined()
  })

  it('Tab am letzten fokussierbaren Element im Drawer springt zyklisch zum ersten (Slice 7.3.2 Focus-Trap)', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openMobileNav()
    await nextTick()
    await nextTick()

    const drawer = wrapper.find('[data-app-shell-drawer]').element as HTMLElement
    const focusableSelector =
      'button:not([disabled]), [href]:not([aria-disabled="true"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    const focusables = Array.from(drawer.querySelectorAll<HTMLElement>(focusableSelector))
    expect(focusables.length).toBeGreaterThan(1)
    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    last.focus()
    expect(document.activeElement).toBe(last)

    drawer.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    await nextTick()

    expect(document.activeElement).toBe(first)

    wrapper.unmount()
  })

  it('Shift+Tab am ersten fokussierbaren Element im Drawer springt zyklisch zum letzten (Slice 7.3.2 Focus-Trap)', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { plugins: [router, pinia, i18n] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openMobileNav()
    await nextTick()
    await nextTick()

    const drawer = wrapper.find('[data-app-shell-drawer]').element as HTMLElement
    const focusableSelector =
      'button:not([disabled]), [href]:not([aria-disabled="true"]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    const focusables = Array.from(drawer.querySelectorAll<HTMLElement>(focusableSelector))
    const first = focusables[0]
    const last = focusables[focusables.length - 1]

    first.focus()
    expect(document.activeElement).toBe(first)

    drawer.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true }),
    )
    await nextTick()

    expect(document.activeElement).toBe(last)

    wrapper.unmount()
  })

  it('kein horizontales Scrollen des Dokuments bei Viewport 320x800 (Slice 7.3 320-px-Gate)', async () => {
    await router.push('/')
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(AppShell, {
      global: { plugins: [router, pinia, i18n] },
    })

    // document.documentElement.clientWidth simuliert 320-px-Viewport
    Object.defineProperty(document.documentElement, 'clientWidth', {
      configurable: true,
      get: () => 320,
    })
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      get: () => 320,
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openMobileNav()
    await wrapper.vm.$nextTick()

    // AppShell-Wurzel darf nicht breiter als der Viewport sein
    const root = wrapper.element as HTMLElement
    expect(root.scrollWidth).toBeLessThanOrEqual(320)
    // Body-Scroll-Lock ist gesetzt (overflow:hidden verhindert Document-Scroll)
    expect(document.body.style.overflow).toBe('hidden')
  })
})
