/**
 * App.vue — Einstellungsfenster als Hintergrundroute (#1799, Etappe 3).
 *
 * Auf `/settings/:section` (meta.settingsWindow) rendert der Haupt-router-view
 * die gemerkte vorherige Ansicht, bei Direktaufruf die Bibliothek der Laeufe;
 * das Fenster selbst kommt aus einem zweiten router-view.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { useSettingsWindowStore } from '@/stores/settingsWindow'

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
      {
        path: '/settings/:section',
        name: 'SettingsWindow',
        component: view('window-stub'),
        meta: { settingsWindow: true },
      },
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
  return { wrapper, router }
}

describe('App.vue — Einstellungsfenster über der vorherigen Ansicht', () => {
  it('lässt die Ansicht darunter stehen und zeigt das Fenster darüber', async () => {
    const { wrapper } = await mountApp('/settings/system', '/library/graphs')
    expect(wrapper.find('.graphs-view').exists()).toBe(true)
    expect(wrapper.find('.runs-view').exists()).toBe(false)
    expect(wrapper.find('.window-stub').exists()).toBe(true)
  })

  it('Direktaufruf (nichts gemerkt) legt das Fenster über /library/runs', async () => {
    const { wrapper } = await mountApp('/settings/system', null)
    expect(wrapper.find('.runs-view').exists()).toBe(true)
    expect(wrapper.find('.window-stub').exists()).toBe(true)
  })

  it('ohne Fenster-Route: keine Hintergrundroute, kein Fenster', async () => {
    const { wrapper } = await mountApp('/library/graphs', '/library/runs')
    expect(wrapper.find('.graphs-view').exists()).toBe(true)
    expect(wrapper.find('.window-stub').exists()).toBe(false)
  })

  it('der Hintergrund bleibt beim Abschnittswechsel stehen', async () => {
    const { wrapper, router } = await mountApp('/settings/system', '/library/graphs')
    await router.replace('/settings/budgets')
    await flushPromises()
    expect(wrapper.find('.graphs-view').exists()).toBe(true)
    expect(wrapper.find('.window-stub').exists()).toBe(true)
  })

  it('Browser-Zurück schließt das Fenster: die Ansicht darunter bleibt, das Fenster verschwindet', async () => {
    const { wrapper, router } = await mountApp('/library/graphs', null)
    await router.push('/settings/system')
    useSettingsWindowStore().open('/library/graphs')
    await flushPromises()
    expect(wrapper.find('.window-stub').exists()).toBe(true)
    router.back()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/library/graphs')
    expect(wrapper.find('.window-stub').exists()).toBe(false)
    expect(wrapper.find('.graphs-view').exists()).toBe(true)
  })
})
