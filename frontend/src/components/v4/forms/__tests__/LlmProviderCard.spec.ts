import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import LlmProviderCard from '../LlmProviderCard.vue'

const messages = {
  de: {
    settings: {
      v4: {
        llmProvider: {
          title: 'LLM-Anbieter',
          subtitle: '',
          baseUrlLabel: 'Base URL',
          apiKeyLabel: 'API Key',
          modelLabel: 'Modell',
          saveBtn: 'Speichern',
          savedHint: 'Gespeichert.',
          presets: {
            ollama: 'Ollama (lokal)',
            openai: 'OpenAI',
            gemini: 'Gemini',
            anthropic: 'Anthropic',
            custom: 'Eigener Endpunkt',
          },
        },
      },
    },
  },
}

const mockDraft = reactive<Record<string, unknown>>({
  LLM_BASE_URL: 'http://localhost:11434/v1',
  LLM_API_KEY: '',
  LLM_MODEL_NAME: 'qwen2.5:32b',
})

const mockStore = {
  draft: mockDraft,
  saveSettings: vi.fn().mockResolvedValue(undefined),
}

vi.mock('@/store/settings', () => ({
  useSettingsStore: vi.fn(() => mockStore),
}))

import { useSettingsStore } from '@/store/settings'

describe('LlmProviderCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockDraft['LLM_BASE_URL'] = 'http://localhost:11434/v1'
    mockDraft['LLM_API_KEY'] = ''
    mockDraft['LLM_MODEL_NAME'] = 'qwen2.5:32b'
    mockStore.saveSettings = vi.fn().mockResolvedValue(undefined)
  })

  function wrap() {
    return mount(LlmProviderCard, {
      global: {
        plugins: [createI18n({ legacy: false, locale: 'de', messages })],
        stubs: { Card: { template: '<div><slot /></div>' } },
      },
    })
  }

  it('rendert alle 5 Preset-Buttons', () => {
    const w = wrap()
    expect(w.findAll('.llm-preset')).toHaveLength(5)
  })

  it('Ollama-Preset ist initial aktiv (matching URL)', () => {
    const w = wrap()
    const buttons = w.findAll('.llm-preset')
    expect(buttons[0].classes()).toContain('llm-preset--active')
  })

  it('Klick auf OpenAI → LLM_BASE_URL = OpenAI-URL, API-Key-Feld sichtbar', async () => {
    const store = vi.mocked(useSettingsStore)()
    const w = wrap()
    const buttons = w.findAll('.llm-preset')
    await buttons[1].trigger('click') // OpenAI
    expect(store.draft['LLM_BASE_URL']).toBe('https://api.openai.com/v1')
    await flushPromises()
    expect(w.find('#llm-api-key').exists()).toBe(true)
  })

  it('Klick auf Ollama → API-Key-Feld nicht sichtbar, LLM_API_KEY gecleart', async () => {
    const store = vi.mocked(useSettingsStore)()
    store.draft['LLM_BASE_URL'] = 'https://api.openai.com/v1'
    const w = wrap()
    const buttons = w.findAll('.llm-preset')
    await buttons[0].trigger('click') // Ollama
    expect(store.draft['LLM_API_KEY']).toBe('')
    await flushPromises()
    expect(w.find('#llm-api-key').exists()).toBe(false)
  })

  it('Speichern-Button ruft store.saveSettings() auf', async () => {
    const store = vi.mocked(useSettingsStore)()
    const w = wrap()
    await w.find('.v4-btn--primary').trigger('click')
    await flushPromises()
    expect(store.saveSettings).toHaveBeenCalledTimes(1)
    expect(store.saveSettings).toHaveBeenCalledWith({ confirmSecrets: true })
  })
})
