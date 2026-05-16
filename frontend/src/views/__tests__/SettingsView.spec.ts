import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

import de from '../../i18n/locales/de.json'
import en from '../../i18n/locales/en.json'

vi.mock('../../components/AppFooter.vue', () => ({
  default: { name: 'AppFooter', template: '<footer />' },
}))
vi.mock('../../components/ui/AgoraGlyph.vue', () => ({
  default: { name: 'AgoraGlyph', template: '<svg />' },
}))
vi.mock('../../api/settings', () => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  openSettingsStream: vi.fn().mockResolvedValue({ close: vi.fn() }),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
}))
vi.mock('../../api/llmRouting', () => ({
  listLlmProviders: vi.fn().mockResolvedValue([]),
  listProviderModels: vi.fn().mockResolvedValue([]),
  getActiveLlmConfig: vi.fn().mockResolvedValue({}),
  setActiveLlmConfig: vi.fn().mockResolvedValue({}),
}))

import {
  fetchSettings,
  fetchSettingsSchema,
} from '../../api/settings'
import { useSettingsStore } from '../../store/settings'
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
  ;(fetchSettingsSchema as ReturnType<typeof vi.fn>).mockResolvedValue({
    success: true,
    data: {
      sections: ['llm', 'ui', 'security'],
      fields: [
        { key: 'LLM_MODEL_NAME', section: 'llm', type: 'string', secret: false, reload_required: false, default: 'qwen2.5:32b' },
        { key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int', secret: false, reload_required: false, default: 5000, min: 1000, max: 60000 },
        { key: 'NEO4J_PASSWORD', section: 'security', type: 'string', secret: true, reload_required: true, default: null },
      ],
    },
  })
  ;(fetchSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
    success: true,
    data: {
      sections: ['llm', 'ui', 'security'],
      fields: {
        llm: [{
          key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
          secret: false, reload_required: false,
          value: 'qwen2.5:32b', default: 'qwen2.5:32b',
          source: 'env', is_set: true,
        }],
        ui: [{
          key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int',
          secret: false, reload_required: false,
          value: 5000, default: 5000,
          source: 'default', is_set: true,
        }],
        security: [{
          key: 'NEO4J_PASSWORD', section: 'security', type: 'string',
          secret: true, reload_required: true,
          value: null, source: 'env', is_set: true,
        }],
      },
    },
  })
}

async function mountView(locale = 'de') {
  const router = makeRouter()
  const i18n = makeI18n(locale)
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(SettingsView, {
    global: {
      plugins: [router, i18n, pinia],
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

describe('SettingsView', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    buildResponses()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  it('rendert die Sektions-Tabs inklusive UI-Sektion aus dem Backend-Schema', async () => {
    const wrapper = await mountView()
    const tabLabels = wrapper.findAll('[role="tab"]').map((el) => el.text())
    expect(tabLabels).toEqual(['LLM-Auswahl', 'LLM', 'UI', 'Secrets'])
  })

  it('rendert Secret-Field als password-Input ohne Klartext', async () => {
    const wrapper = await mountView()
    // Tab 0 = LLM-Auswahl (default), Tab 3 = Secrets in [LLM-Auswahl, llm, ui, security]
    await wrapper.findAll('[role="tab"]')[3].trigger('click')
    const secretInput = wrapper.find<HTMLInputElement>('input[type="password"]')
    expect(secretInput.exists()).toBe(true)
    expect(secretInput.element.value).toBe('')
    expect(secretInput.attributes('placeholder')).toContain('gesetzt')
    expect(wrapper.html()).not.toContain('plaintext-canary')
  })

  it('zeigt Inline-Validation-Hints aus dem Pinia-Store', async () => {
    const wrapper = await mountView()
    // LLM-Auswahl-Panel hat keine Schema-Fields; auf LLM-Tab wechseln (Index 1).
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    const store = useSettingsStore()
    store.validationErrors = [
      { key: 'LLM_MODEL_NAME', code: 'type_error', message: 'Mein Validation-Hint' },
    ]
    await wrapper.vm.$nextTick()
    const hints = wrapper.findAll('.hint--error').map((el) => el.text())
    expect(hints).toContain('Mein Validation-Hint')
  })

  it('rendert englische Labels, wenn die UI-Sprache EN ist', async () => {
    const wrapper = await mountView('en')
    expect(wrapper.find('h1.title').text()).toBe('Settings')
    const tabLabels = wrapper.findAll('[role="tab"]').map((el) => el.text())
    expect(tabLabels).toEqual(['LLM selection', 'LLM', 'UI', 'Secrets'])
  })
})
