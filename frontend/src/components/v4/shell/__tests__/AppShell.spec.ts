/**
 * AppShell — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Mountet ohne Crash.
 * 2. Sidebar-Slot wird gerendert.
 * 3. Topbar-Slot wird gerendert.
 * 4. Default-Main-Slot wird gerendert.
 * 5. Inspector-Slot ist default geschlossen.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { makeTestRouter } from './testRouter'

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

  it('mountet ohne Crash', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia()] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert Standard-Sidebar-Slot (Sidebar-Komponente)', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia()] },
    })
    // Sidebar hat class app-shell__sidebar
    expect(wrapper.find('.app-shell__sidebar').exists()).toBe(true)
  })

  it('rendert Topbar-Slot', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia()] },
    })
    expect(wrapper.find('.app-shell__topbar').exists()).toBe(true)
  })

  it('rendert benannten Sidebar-Slot-Inhalt', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      slots: {
        sidebar: '<div class="custom-sidebar">Sidebar</div>',
      },
      global: { plugins: [router, createPinia()] },
    })
    expect(wrapper.find('.custom-sidebar').exists()).toBe(true)
  })

  it('rendert Main-Default-Slot-Inhalt', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      slots: {
        default: '<div class="main-content">Main</div>',
      },
      global: { plugins: [router, createPinia()] },
    })
    expect(wrapper.find('.main-content').exists()).toBe(true)
  })

  it('Inspector-Slot ist default geschlossen', async () => {
    await router.push('/')
    const wrapper = mount(AppShell, {
      global: { plugins: [router, createPinia()] },
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
      global: { plugins: [router, pinia] },
    })

    const { useShellStore } = await import('@/stores/shell')
    const store = useShellStore()
    store.openInspector()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.app-shell__inspector').exists()).toBe(true)
    expect(wrapper.find('.inspector-content').exists()).toBe(true)
  })
})
