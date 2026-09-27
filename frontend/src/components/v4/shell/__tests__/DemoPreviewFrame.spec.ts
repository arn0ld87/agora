/**
 * DemoPreviewFrame — Demo-Vorschau fuer Betreiber-Routen (BYOK-Demoinstanz).
 *
 * Prueft:
 * 1. Passthrough ohne Banner/Sperre fuer Betreiber (operatorAccess=true).
 * 2. Banner + inert-gesperrter, ausgegrauter Slot fuer Besucher auf
 *    operatorOnly-Routen ohne demoPreview:'static'.
 * 3. Statische Erklaerkarte statt der echten Ansicht bei demoPreview:'static'.
 * 4. Passthrough fuer Routen ohne meta.operatorOnly, unabhaengig vom Zugang.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import DemoPreviewFrame from '../DemoPreviewFrame.vue'
import { useAuthStore } from '@/store/auth'
import type { AuthConfigResponse } from '@/contracts/authConfigContract'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const SUPABASE_CONFIG: AuthConfigResponse = {
  auth_backend: 'supabase',
  jwt_enabled: true,
  supabase_url: null,
  supabase_anon_key: null,
  realtime_enabled: false,
}

const ViewStub = { template: '<div class="real-view">Echte Ansicht</div>' }

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', name: 'Dashboard', component: ViewStub },
      { path: '/workspace/provider-keys', name: 'WorkspaceProviderKeys', component: ViewStub },
      {
        path: '/settings/general',
        name: 'SettingsGeneral',
        component: ViewStub,
        meta: { operatorOnly: true },
      },
      {
        path: '/settings/api-keys',
        name: 'SettingsApiKeys',
        component: ViewStub,
        meta: { operatorOnly: true, demoPreview: 'static' },
      },
    ],
  })
}

async function mountFrame(path: string, asVisitor: boolean) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  if (asVisitor) {
    auth.config = SUPABASE_CONFIG
    auth.session = { access_token: 'tok', user: { id: 'u1' } } as never
  }
  const router = makeRouter()
  await router.push(path)
  await router.isReady()

  return mount(
    {
      components: { DemoPreviewFrame },
      template: '<DemoPreviewFrame><div class="slot-content">Inhalt</div></DemoPreviewFrame>',
    },
    { global: { plugins: [router, pinia, i18n] } },
  )
}

describe('DemoPreviewFrame', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('rendert den Slot unveraendert fuer Betreiber (operatorAccess=true)', async () => {
    const wrapper = await mountFrame('/settings/general', false)
    expect(wrapper.find('.slot-content').exists()).toBe(true)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('rendert den Slot unveraendert auf Routen ohne meta.operatorOnly, auch fuer Besucher', async () => {
    const wrapper = await mountFrame('/dashboard', true)
    expect(wrapper.find('.slot-content').exists()).toBe(true)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('zeigt Banner + gesperrten, ausgegrauten Slot fuer Besucher auf einer operatorOnly-Route ohne demoPreview:static', async () => {
    const wrapper = await mountFrame('/settings/general', true)
    const banner = wrapper.find('[role="status"]')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('Demo-Vorschau')
    const content = wrapper.find('.demo-preview__content')
    expect(content.exists()).toBe(true)
    expect(content.attributes('inert')).not.toBeUndefined()
    expect(wrapper.find('.slot-content').exists()).toBe(true)
  })

  it('zeigt eine statische Erklaerkarte statt der echten Ansicht bei demoPreview:static', async () => {
    const wrapper = await mountFrame('/settings/api-keys', true)
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    expect(wrapper.find('.demo-preview__static').exists()).toBe(true)
    // Die echte Ansicht (Slot-Inhalt) wird gar nicht erst gemountet.
    expect(wrapper.find('.slot-content').exists()).toBe(false)
    expect(wrapper.text()).toContain('API-Schlüssel')
  })

  it('Link zu den eigenen Provider-Keys ist im Banner vorhanden', async () => {
    const wrapper = await mountFrame('/settings/general', true)
    const link = wrapper.find('.demo-preview__banner-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/workspace/provider-keys')
  })
})
