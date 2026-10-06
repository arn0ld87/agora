/**
 * Einstellungsfenster, Etappe 3 (#1799): Abschnitte Anbieter, Profile, Allgemein.
 *
 * Prüft die Zusammensetzung (welche Bestandsansicht wo hängt), die Rollen
 * (Betreiber, angemeldet ohne Betreiberrecht, Demo), den Wegfall doppelter
 * Überschriften und dass der Profil-Manager von Allgemein zu Profile wandert.
 * Die großen Bestandsansichten sind gestubbt; ihr Verhalten prüfen ihre
 * eigenen Specs.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { useAuthStore } from '@/store/auth'
import type { AuthConfigResponse } from '@/contracts/authConfigContract'
import { GENERAL_SETTINGS_SECTIONS, PROFILE_SETTINGS_SECTIONS } from '@/views/Settings/settingsSections'

vi.mock('@/views/Settings/LlmProvidersView.vue', () => ({
  default: {
    name: 'LlmProvidersView',
    props: ['embedded'],
    template: '<div data-testid="providers-view" :data-embedded="String(embedded !== undefined && embedded !== false)">Anbieterliste</div>',
  },
}))
vi.mock('@/views/Settings/WorkspaceProviderKeysView.vue', () => ({
  default: {
    name: 'WorkspaceProviderKeysView',
    props: ['embedded'],
    template: '<div data-testid="keys-view" :data-embedded="String(embedded !== undefined && embedded !== false)">Schlüssel</div>',
  },
}))
vi.mock('@/views/Settings/LlmRoutingView.vue', () => ({
  default: {
    name: 'LlmRoutingView',
    props: ['embedded'],
    template: '<div data-testid="routing-view" :data-embedded="String(embedded !== undefined && embedded !== false)">Routing</div>',
  },
}))
vi.mock('@/components/v4/forms/LlmProfileManager.vue', () => ({
  default: { name: 'LlmProfileManager', template: '<div data-testid="profile-manager">Profil-Manager</div>' },
}))
vi.mock('@/components/v4/forms/SettingsSectionPanel.vue', () => ({
  default: {
    name: 'SettingsSectionPanel',
    props: ['allowedSections'],
    template: '<div data-testid="section-panel" :data-sections="allowedSections.join(\',\')" />',
  },
}))
vi.mock('@/components/v4/forms/AiModelPicker.vue', () => ({
  default: { name: 'AiModelPicker', template: '<div data-testid="model-picker" />' },
}))
vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: { value: null },
    ensureLoaded: vi.fn().mockResolvedValue(undefined),
    setGlobalSelection: vi.fn().mockResolvedValue(undefined),
  }),
}))

import SectionProviders from '../sections/SectionProviders.vue'
import SectionProfiles from '../sections/SectionProfiles.vue'
import SectionGeneral from '../sections/SectionGeneral.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const SUPABASE_CONFIG: AuthConfigResponse = {
  auth_backend: 'supabase',
  jwt_enabled: true,
  supabase_url: null,
  supabase_anon_key: null,
  realtime_enabled: false,
  demo_mode: false,
}

let wrapper: VueWrapper | null = null

async function mountSection(
  component: object,
  role: 'operator' | 'signedIn' | 'demo' = 'operator',
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (role !== 'operator') {
    const auth = useAuthStore()
    auth.config = { ...SUPABASE_CONFIG, demo_mode: role === 'demo' }
    auth.session = { access_token: 'tok', user: { id: 'u1' } } as never
  }
  wrapper = mount(component, { global: { plugins: [pinia, i18n] } })
  await flushPromises()
  return wrapper
}

describe('Abschnitte Anbieter, Profile, Allgemein', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })
  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  describe('Anbieter', () => {
    it('Betreiber: Anbieterverwaltung und eigene Schlüssel, beide eingebettet', async () => {
      const w = await mountSection(SectionProviders)
      expect(w.find('[data-testid="providers-view"]').attributes('data-embedded')).toBe('true')
      expect(w.find('[data-testid="keys-view"]').attributes('data-embedded')).toBe('true')
      expect(w.find('[data-testid="providers-operator-locked"]').exists()).toBe(false)
    })

    it.each(['signedIn', 'demo'] as const)(
      '%s ohne Betreiberrecht: Verwaltung nicht gerendert, Schlüssel bleiben erreichbar',
      async (role) => {
        const w = await mountSection(SectionProviders, role)
        expect(w.find('[data-testid="providers-view"]').exists()).toBe(false)
        expect(w.find('[data-testid="providers-operator-locked"]').text()).toContain('gehört dem Betreiber')
        expect(w.find('[data-testid="keys-view"]').exists()).toBe(true)
      },
    )

    it('trägt keine eigene Hauptüberschrift', async () => {
      const w = await mountSection(SectionProviders)
      expect(w.find('h1').exists()).toBe(false)
    })
  })

  describe('Profile', () => {
    it('zeigt Profil-Manager, Standardmodell je Stufe und die LLM-Werte', async () => {
      const w = await mountSection(SectionProfiles)
      expect(w.find('[data-testid="profile-manager"]').exists()).toBe(true)
      expect(w.find('[data-testid="routing-view"]').attributes('data-embedded')).toBe('true')
      expect(w.find('[data-testid="section-panel"]').attributes('data-sections')).toBe('llm')
      expect(w.text()).toContain('Standardmodell je Stufe')
      expect(w.find('h1').exists()).toBe(false)
    })

    it('der Abschnitt llm gehört zu Profile und nicht mehr zu Allgemein', () => {
      expect([...PROFILE_SETTINGS_SECTIONS]).toEqual(['llm'])
      expect((GENERAL_SETTINGS_SECTIONS as readonly string[]).includes('llm')).toBe(false)
    })
  })

  describe('Allgemein', () => {
    it('zeigt die Standard-Einstellungen ohne llm und ohne Profil-Manager', async () => {
      const w = await mountSection(SectionGeneral)
      const sections = w.find('[data-testid="section-panel"]').attributes('data-sections') ?? ''
      expect(sections.split(',')).toEqual(['logging', 'locale', 'ui', 'event_bus', 'security'])
      expect(w.find('[data-testid="profile-manager"]').exists()).toBe(false)
    })

    it('eingebettet ohne eigenes h1', async () => {
      const w = await mountSection(SectionGeneral)
      expect(w.find('h1').exists()).toBe(false)
    })
  })
})
