/**
 * App.vue — Startdialog „Neuer Lauf“ nutzt denselben Fenster-Mechanismus wie das
 * Einstellungsfenster (meta.windowOverBackground, #1799 Etappe 3).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { isWindowRoute, useSettingsWindowStore } from '@/stores/settingsWindow'
import realRouter from '@/router'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

vi.mock('@/components/v4/shell/AppShell.vue', () => ({
  default: { name: 'AppShell', props: ['demoFrame'], template: '<div class="shell-stub"><slot /></div>' },
}))
vi.mock('@/components/LogDrawer.vue', () => ({
  default: { name: 'LogDrawer', props: ['open'], template: '<div class="log-drawer-stub" />' },
}))

import App from '../App.vue'

const view = (cls: string) => ({ template: `<div class="${cls}">${cls}</div>` })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/library/runs', name: 'LibraryRuns', component: view('runs-view') },
      { path: '/library/graphs', name: 'LibraryGraphs', component: view('graphs-view') },
      { path: '/library/runs/new', name: 'NewRun', component: view('window-stub'), meta: { windowOverBackground: true } },
      { path: '/settings/:section', name: 'SettingsWindow', component: view('settings-stub'), meta: { settingsWindow: true } },
    ],
  })
}

async function mountApp(path: string, returnTo: string | null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSettingsWindowStore().open(returnTo)
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router, pinia, i18n] } })
  await flushPromises()
  return { wrapper }
}

describe('App.vue — Startdialog über der vorherigen Ansicht', () => {
  it('lässt die Ansicht darunter stehen und zeigt den Dialog darüber', async () => {
    const { wrapper } = await mountApp('/library/runs/new', '/library/graphs')
    expect(wrapper.find('.graphs-view').exists()).toBe(true)
    expect(wrapper.find('.window-stub').exists()).toBe(true)
    expect(wrapper.find('.runs-view').exists()).toBe(false)
  })

  it('Direktaufruf (nichts gemerkt) legt den Dialog über /library/runs', async () => {
    const { wrapper } = await mountApp('/library/runs/new', null)
    expect(wrapper.find('.runs-view').exists()).toBe(true)
    expect(wrapper.find('.window-stub').exists()).toBe(true)
  })

  it('nie ein Fenster unter dem Fenster', async () => {
    const { wrapper } = await mountApp('/library/runs/new', '/settings/system')
    expect(wrapper.find('.runs-view').exists()).toBe(true)
    expect(wrapper.find('.settings-stub').exists()).toBe(false)
  })
})

describe('isWindowRoute und echte Route', () => {
  it('erkennt beide Fenster-Merkmale', () => {
    expect(isWindowRoute({ settingsWindow: true })).toBe(true)
    expect(isWindowRoute({ windowOverBackground: true })).toBe(true)
    expect(isWindowRoute({})).toBe(false)
    expect(isWindowRoute(undefined)).toBe(false)
  })

  it('die Route NewRun behält Pfad und Namen und trägt das Fenster-Merkmal', () => {
    const route = realRouter.getRoutes().find((r) => r.name === 'NewRun')
    expect(route?.path).toBe('/library/runs/new')
    expect(route?.meta.windowOverBackground).toBe(true)
  })
})
