import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import SidebarGroup from '../SidebarGroup.vue'
import { useSidebarState } from '@/composables/useSidebarState'

// localStorage-Mock (Bun-Testrunner hat kein jsdom built-in)
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => { delete store[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

function buildRouter(path: string) {
  const r = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Dashboard', component: { template: '<div/>' } },
      { path: '/settings', name: 'Settings', component: { template: '<div/>' } },
      { path: '/settings/llm-routing', name: 'SettingsLlmRouting', component: { template: '<div/>' } },
    ],
  })
  r.push(path)
  return r
}

describe('SidebarGroup', () => {
  beforeEach(() => {
    localStorage.clear()
    useSidebarState._resetForTesting()
  })

  it('rendert Label', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: { groupKey: 'settings', label: 'Settings', activeRouteNames: [] },
      global: { plugins: [router] },
    })
    expect(w.text()).toContain('Settings')
  })

  it('öffnet/schließt beim Klick auf Trigger', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: { groupKey: 'sg-test', label: 'Test', activeRouteNames: [] },
      slots: { default: '<div class="child">Child</div>' },
      global: { plugins: [router] },
    })
    // Initial geschlossen (kein localStorage-State)
    expect(w.find('.child').exists()).toBe(false)
    await w.find('[data-sidebar-trigger]').trigger('click')
    expect(w.find('.child').exists()).toBe(true)
  })

  it('öffnet automatisch wenn aktive Route in activeRouteNames', async () => {
    const router = buildRouter('/settings/llm-routing')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: {
        groupKey: 'settings',
        label: 'Settings',
        activeRouteNames: ['Settings', 'SettingsLlmRouting'],
      },
      slots: { default: '<div class="child">Child</div>' },
      global: { plugins: [router] },
    })
    await w.vm.$nextTick()
    expect(w.find('.child').exists()).toBe(true)
  })

  it('persistiert State in localStorage', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: { groupKey: 'sg-persist', label: 'Persist', activeRouteNames: [] },
      global: { plugins: [router] },
    })
    await w.find('[data-sidebar-trigger]').trigger('click')
    const raw = localStorage.getItem('agora.sidebar.v1')
    expect(JSON.parse(raw!)['sg-persist']).toBe(true)
  })

  it('Trigger trägt aria-expanded=false initial und aria-expanded=true nach Öffnen', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: { groupKey: 'sg-aria', label: 'Aria', activeRouteNames: [] },
      global: { plugins: [router] },
    })
    const trigger = w.find('[data-sidebar-trigger]')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
  })

  it('Trigger hat aria-controls pointing auf Body-Element', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: { groupKey: 'sg-ctrl', label: 'Ctrl', activeRouteNames: [] },
      slots: { default: '<div class="child">Child</div>' },
      global: { plugins: [router] },
    })
    const trigger = w.find('[data-sidebar-trigger]')
    expect(trigger.attributes('aria-controls')).toBe('sidebar-group-body-sg-ctrl')
    // Body-ID nach Öffnen vorhanden
    await trigger.trigger('click')
    const body = w.find('#sidebar-group-body-sg-ctrl')
    expect(body.exists()).toBe(true)
  })

  it('watch: Auto-Open wenn Route auf aktive Child-Route wechselt', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const w = mount(SidebarGroup, {
      props: {
        groupKey: 'sg-watch',
        label: 'Watch',
        activeRouteNames: ['Settings', 'SettingsLlmRouting'],
      },
      slots: { default: '<div class="child">Child</div>' },
      global: { plugins: [router] },
    })
    // Initial: Route '/' → nicht aktiv → geschlossen
    await w.vm.$nextTick()
    expect(w.find('.child').exists()).toBe(false)
    // Route wechseln zu Settings
    await router.push('/settings')
    await w.vm.$nextTick()
    expect(w.find('.child').exists()).toBe(true)
  })
})
