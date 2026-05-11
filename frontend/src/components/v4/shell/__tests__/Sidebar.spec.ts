/**
 * Sidebar — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Rendert nav-Items.
 * 2. Active-State haengt an active-Prop.
 * 3. Collapse-Click emittet collapse-toggle.
 * 4. Settings-Group toggelt via settingsOpen-Prop.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

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

import Sidebar from '../Sidebar.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'Home', component: { template: '<div/>' } },
    { path: '/runs', name: 'Runs', component: { template: '<div/>' } },
    { path: '/settings', name: 'Settings', component: { template: '<div/>' } },
    { path: '/settings/llm-routing', name: 'SettingsLlmRouting', component: { template: '<div/>' } },
  ],
})

describe('Sidebar', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
  })

  it('mountet ohne Crash', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('rendert Brand-Wordmark "Agora"', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('Agora')
  })

  it('rendert Workspace-Nav-Items (Dashboard, Runs vorhanden)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router] },
    })
    const text = wrapper.text()
    expect(text).toContain('Dashboard')
    expect(text).toContain('Runs')
  })

  it('rendert Settings-Gruppe', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router] },
    })
    expect(wrapper.text()).toContain('Settings')
  })

  it('Active-State via active-Prop "dashboard"', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { active: 'dashboard' },
      global: { plugins: [router] },
    })
    // SidebarItem mit active wird mit Klasse sidebar-item--active gerendert
    const activeItems = wrapper.findAll('.sidebar-item--active')
    expect(activeItems.length).toBeGreaterThan(0)
  })

  it('kein active-Item wenn active="" (leerer String)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { active: '' },
      global: { plugins: [router] },
    })
    const activeItems = wrapper.findAll('.sidebar-item--active')
    expect(activeItems.length).toBe(0)
  })

  it('Collapse-Footer-Click emittet collapse-toggle', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router] },
    })
    await wrapper.find('.sidebar__footer').trigger('click')
    expect(wrapper.emitted('collapse-toggle')).toBeTruthy()
  })

  it('Settings-Sub-Items sichtbar wenn settingsOpen=true', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { settingsOpen: true },
      global: { plugins: [router] },
    })
    const text = wrapper.text()
    expect(text).toContain('General')
    expect(text).toContain('LLM Routing')
  })

  it('Settings-Sub-Items ausgeblendet wenn settingsOpen=false', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { settingsOpen: false },
      global: { plugins: [router] },
    })
    const text = wrapper.text()
    expect(text).not.toContain('General')
  })
})
