/**
 * App.vue — Route↔Static-Vorschau-Swap (#1697, Teil B).
 *
 * App.vue selbst entscheidet nur noch, OB die Route-Komponente durch
 * DemoPreviewStaticView ersetzt wird (meta.demoPreview:'static' UND
 * auth.demoPreview) — Betreiber-Sperre/Banner fuer alle anderen
 * operatorOnly-Routen lebt seit diesem PR in AppShell.vue/DemoPreviewFrame.vue
 * (siehe deren eigene Specs). Prueft:
 * 1. Statische Route + demoPreview aktiv → DemoPreviewStaticView statt
 *    Route-Komponente, die echte View mountet nicht.
 * 2. Statische Route ohne demoPreview (kein Demo-Modus) → echte View mountet.
 * 3. Nicht-statische operatorOnly-Route + demoPreview aktiv → echte View
 *    mountet unveraendert (App.vue greift dort nicht ein).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { useAuthStore } from '@/store/auth'
import type { AuthConfigResponse } from '@/contracts/authConfigContract'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

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

vi.mock('@/components/v4/shell/DemoPreviewStaticView.vue', () => ({
  default: { name: 'DemoPreviewStaticView', template: '<div class="static-stub">Static</div>' },
}))
vi.mock('@/components/LogDrawer.vue', () => ({
  default: { name: 'LogDrawer', props: ['open'], template: '<div class="log-drawer-stub" />' },
}))

import App from '../App.vue'

const RealViewStub = { template: '<div class="real-view">Echte Ansicht</div>' }

const DEMO_CONFIG: AuthConfigResponse = {
  auth_backend: 'supabase',
  jwt_enabled: true,
  supabase_url: null,
  supabase_anon_key: null,
  realtime_enabled: false,
  demo_mode: true,
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/settings/api-keys',
        name: 'SettingsApiKeys',
        component: RealViewStub,
        meta: { operatorOnly: true, demoPreview: 'static' },
      },
      {
        path: '/settings/general',
        name: 'SettingsGeneral',
        component: RealViewStub,
        meta: { operatorOnly: true },
      },
    ],
  })
}

async function mountApp(path: string, demoMode: boolean) {
  lsMock.clear()
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.config = demoMode ? DEMO_CONFIG : { ...DEMO_CONFIG, demo_mode: false }
  auth.session = { access_token: 'tok', user: { id: 'u1' } } as never
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router, pinia, i18n] } })
  await flushPromises()
  return wrapper
}

describe('App.vue — Static-Vorschau-Swap', () => {
  it('rendert DemoPreviewStaticView statt der echten View bei demoPreview:static + aktiver Vorschau', async () => {
    const wrapper = await mountApp('/settings/api-keys', true)
    expect(wrapper.find('.static-stub').exists()).toBe(true)
    expect(wrapper.find('.real-view').exists()).toBe(false)
  })

  it('rendert die echte View, wenn demo_mode false ist (kein Demo-Modus)', async () => {
    const wrapper = await mountApp('/settings/api-keys', false)
    expect(wrapper.find('.static-stub').exists()).toBe(false)
    expect(wrapper.find('.real-view').exists()).toBe(true)
  })

  it('greift auf nicht-statischen operatorOnly-Routen nicht ein', async () => {
    const wrapper = await mountApp('/settings/general', true)
    expect(wrapper.find('.static-stub').exists()).toBe(false)
    expect(wrapper.find('.real-view').exists()).toBe(true)
  })
})
