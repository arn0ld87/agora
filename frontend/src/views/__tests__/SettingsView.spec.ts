// Issue #133 / SUB4 — SettingsView-Smoke-Tests.
//
// Decken die UI-Verträge, die den Issue-Akzeptanzkriterien entsprechen:
//  - Render der Sektions-Tabs aus dem Backend-Schema.
//  - Reload-erforderlich-Badge erscheint pro Field mit reload_required.
//  - Secret-Field rendert ein password-Input und niemals den Klartext.
//  - Validation-Errors aus dem Store landen als Inline-Hint im DOM.
//
// Wir mocken die API auf Modulebene und füttern den Store damit. Vue
// Router ist als createMemoryHistory eingebunden, weil ``useRouter``
// in der View aufgerufen wird.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import de from '../../i18n/locales/de.json'
import en from '../../i18n/locales/en.json'

// AppFooter importiert beim Modul-Init das globale i18n/index.js, das
// direkt ``localStorage.getItem`` aufruft — das ist im Test-Env nicht
// initialisiert. Wir stubben den Footer komplett aus, damit die
// Module-Resolve-Kette nie an localStorage rührt.
vi.mock('../../components/AppFooter.vue', () => ({
  default: { name: 'AppFooter', template: '<footer />' },
}))
vi.mock('../../components/ui/AgoraGlyph.vue', () => ({
  default: { name: 'AgoraGlyph', template: '<svg />' },
}))

vi.mock('../../api/settings', () => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
}))

import {
  fetchSettings,
  fetchSettingsSchema,
} from '../../api/settings'
import settingsStore from '../../store/settings'
import SettingsView from '../SettingsView.vue'


function makeI18n(locale = 'de') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { de, en },
  })
}


function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/settings', name: 'Settings', component: SettingsView },
    ],
  })
}


function buildResponses() {
  (fetchSettingsSchema as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    data: {
      success: true,
      data: {
        sections: ['llm', 'embedding', 'security'],
        fields: [
          { key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
            secret: false, reload_required: false, default: 'qwen2.5:32b' },
          { key: 'EMBEDDING_MODEL', section: 'embedding', type: 'string',
            secret: false, reload_required: true, default: 'nomic-embed-text' },
          { key: 'NEO4J_PASSWORD', section: 'security', type: 'string',
            secret: true, reload_required: true, default: null },
        ],
      },
    },
  });
  (fetchSettings as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    data: {
      success: true,
      data: {
        sections: ['llm', 'embedding', 'security'],
        fields: {
          llm: [{
            key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
            secret: false, reload_required: false,
            value: 'qwen2.5:32b', default: 'qwen2.5:32b',
            source: 'env', is_set: true,
          }],
          embedding: [{
            key: 'EMBEDDING_MODEL', section: 'embedding', type: 'string',
            secret: false, reload_required: true,
            value: 'nomic-embed-text', default: 'nomic-embed-text',
            source: 'default', is_set: false,
          }],
          security: [{
            key: 'NEO4J_PASSWORD', section: 'security', type: 'string',
            secret: true, reload_required: true,
            value: null, source: 'env', is_set: true,
          }],
        },
      },
    },
  })
}


function resetStore() {
  Object.assign(settingsStore, {
    loading: false,
    saving: false,
    loadError: null,
    saveError: null,
    sections: [],
    schema: [],
    fields: {},
    draft: {},
    drafts_secret_filled: {},
    validationErrors: [],
  })
}


async function mountView(locale = 'de') {
  const router = makeRouter()
  const i18n = makeI18n(locale)
  // AppFooter importiert beim Modul-Init das globale ``i18n/index.js``,
  // das wiederum direkt ``localStorage.getItem`` aufruft. Im Test-Env
  // ist localStorage nicht zwingend initialisiert, deshalb stubben wir
  // AppFooter (für unsere Smoke-Tests irrelevant).
  const wrapper = mount(SettingsView, {
    global: {
      plugins: [router, i18n],
      stubs: {
        AppFooter: true,
        AgoraGlyph: true,
      },
    },
  })
  await router.isReady()
  await flushPromises()
  return wrapper
}


beforeEach(() => {
  vi.resetAllMocks()
  resetStore()
  buildResponses()
})

afterEach(() => {
  vi.resetAllMocks()
})


describe('SettingsView', () => {
  it('rendert die Sektions-Tabs aus dem Backend-Schema', async () => {
    const wrapper = await mountView()
    const tabLabels = wrapper.findAll('[role="tab"]').map((el) => el.text())
    // 3 Sektionen aus dem Mock + i18n-Labels
    expect(tabLabels).toEqual(['LLM', 'Embedding', 'Secrets'])
  })

  it('zeigt Reload-erforderlich-Badge pro Field mit reload_required', async () => {
    const wrapper = await mountView()
    // Embedding-Tab anwählen
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    const badges = wrapper.findAll('.cell-flags .badge')
    const texts = badges.map((b) => b.text())
    expect(texts).toContain('Reload nötig')
  })

  it('rendert Secret-Field als password-Input ohne Klartext', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('[role="tab"]')[2].trigger('click')
    const secretInput = wrapper.find<HTMLInputElement>('input[type="password"]')
    expect(secretInput.exists()).toBe(true)
    expect(secretInput.element.value).toBe('')
    // Placeholder zeigt is_set-Status
    expect(secretInput.attributes('placeholder')).toContain('gesetzt')
    // Im gesamten DOM darf kein NEO4J-Klartext-Wert liegen
    expect(wrapper.html()).not.toContain('plaintext-canary')
  })

  it('zeigt Inline-Validation-Hints aus dem Store', async () => {
    const wrapper = await mountView()
    settingsStore.validationErrors = [
      { key: 'LLM_MODEL_NAME', code: 'type_error', message: 'Mein Validation-Hint' },
    ]
    await wrapper.vm.$nextTick()
    const hints = wrapper.findAll('.hint--error').map((el) => el.text())
    expect(hints).toContain('Mein Validation-Hint')
  })

  it('zeigt das Source-Badge mit dem i18n-Label', async () => {
    const wrapper = await mountView()
    const badges = wrapper.findAll('.cell-source .badge').map((b) => b.text())
    // Erste Sektion (LLM) hat source=env, übersetzt auf ".env"
    expect(badges[0]).toBe('.env')
  })

  it('rendert englische Labels, wenn die UI-Sprache EN ist', async () => {
    const wrapper = await mountView('en')
    expect(wrapper.find('h1.title').text()).toBe('Settings')
    const tabLabels = wrapper.findAll('[role="tab"]').map((el) => el.text())
    expect(tabLabels).toEqual(['LLM', 'Embedding', 'Secrets'])
  })
})
