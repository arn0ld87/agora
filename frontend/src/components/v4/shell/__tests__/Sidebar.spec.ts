/**
 * Sidebar — Smoke-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Rendert nav-Items.
 * 2. Active-State haengt an active-Prop.
 * 3. Collapse-Click emittet collapse-toggle.
 * 4. Settings-Group toggelt via settingsOpen-Prop.
 *
 * Nach i18n-Migration (Slice 06): Labels kommen aus DE-Locale.
 */
import { describe, it, expect, beforeEach } from 'vitest'
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

const router = makeTestRouter()

describe('Sidebar', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
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

  it('Active-State via active-Prop "dashboard"', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { active: 'dashboard' },
      global: { plugins: [router, i18n] },
    })
    // SidebarItem mit active wird mit Klasse sidebar-item--active gerendert
    const activeItems = wrapper.findAll('.sidebar-item--active')
    expect(activeItems.length).toBeGreaterThan(0)
  })

  it('kein active-Item wenn active="" (leerer String)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { active: '' },
      global: { plugins: [router, i18n] },
    })
    const activeItems = wrapper.findAll('.sidebar-item--active')
    expect(activeItems.length).toBe(0)
  })

  it('Collapse-Footer-Click emittet collapse-toggle', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      global: { plugins: [router, i18n] },
    })
    await wrapper.find('.sidebar__footer').trigger('click')
    expect(wrapper.emitted('collapse-toggle')).toBeTruthy()
  })

  it('Settings-Sub-Items sichtbar wenn settingsOpen=true (DE-Labels)', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { settingsOpen: true },
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    // DE-Locale: general="Allgemein", llmRouting="LLM-Routing"
    expect(text).toContain('Allgemein')
    expect(text).toContain('LLM-Routing')
  })

  it('Settings-Sub-Items ausgeblendet wenn settingsOpen=false', async () => {
    await router.push('/')
    const wrapper = mount(Sidebar, {
      props: { settingsOpen: false },
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    expect(text).not.toContain('Allgemein')
  })
})
