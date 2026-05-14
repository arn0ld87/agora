import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createTestingPinia } from '@pinia/testing'
import LlmProfileManager from '../LlmProfileManager.vue'

// Kein echter API-Aufruf in Tests — fetch-Action wird durch createTestingPinia gestubbt.
vi.mock('@/api/llmProfiles', () => ({
  fetchLlmProfiles: vi.fn().mockResolvedValue([]),
  createLlmProfile: vi.fn().mockResolvedValue({}),
  updateLlmProfile: vi.fn().mockResolvedValue({}),
  deleteLlmProfile: vi.fn().mockResolvedValue(undefined),
  setDefaultLlmProfile: vi.fn().mockResolvedValue({}),
}))

const messages = {
  de: {
    settings: {
      v4: {
        llmProfiles: {
          title: 'LLM-Profile',
          subtitle: '',
          addBtn: 'Neues Profil',
          nameLabel: 'Anzeigename',
          providerLabel: 'Anbieter',
          baseUrlLabel: 'Base URL',
          modelLabel: 'Modell',
          apiKeyLabel: 'API Key',
          apiKeyPlaceholderEdit: 'Leer lassen = unverändert',
          clearKeyBtn: 'Key entfernen',
          setDefaultBtn: 'Als Standard setzen',
          defaultBadge: 'Standard',
          deleteConfirm: 'Dieses Profil wirklich löschen?',
          saveBtn: 'Speichern',
          cancelBtn: 'Abbrechen',
          editBtn: 'Bearbeiten',
          deleteBtn: 'Löschen',
          emptyState: 'Noch keine Profile angelegt.',
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

const i18n = createI18n({ legacy: false, locale: 'de', messages })

const PROFILE_A = {
  id: 'p1',
  name: 'Lokales Ollama',
  provider: 'ollama' as const,
  base_url: 'http://localhost:11434/v1',
  model_name: 'qwen2.5:32b',
  api_key: null,
  is_default: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const PROFILE_B = {
  id: 'p2',
  name: 'OpenAI GPT-4o',
  provider: 'openai' as const,
  base_url: 'https://api.openai.com/v1',
  model_name: 'gpt-4o',
  api_key: null,
  is_default: false,
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

function wrap(storeOverrides?: object) {
  return mount(LlmProfileManager, {
    global: {
      plugins: [
        i18n,
        createTestingPinia({
          createSpy: vi.fn,
          initialState: {
            llmProfiles: {
              profiles: [PROFILE_A, PROFILE_B],
              loading: false,
              saving: false,
              error: null,
              ...storeOverrides,
            },
          },
          stubActions: true,
        }),
      ],
      stubs: { Card: { template: '<div><slot /></div>' } },
    },
  })
}

describe('LlmProfileManager', () => {
  it('rendert beide Profile aus dem Pinia-Store', async () => {
    const w = wrap()
    await flushPromises()
    expect(w.text()).toContain('Lokales Ollama')
    expect(w.text()).toContain('OpenAI GPT-4o')
  })

  it('store.create wird mit erwartetem Payload aufgerufen beim Anlegen', async () => {
    const w = wrap()
    await flushPromises()

    // Store-Referenz aus dem aktiven Pinia holen (createTestingPinia hat es registriert)
    const { useLlmProfilesStore } = await import('@/store/llmProfiles')
    const store = useLlmProfilesStore()

    // Neues-Profil-Formular öffnen
    await w.find('button.v4-btn--primary').trigger('click')
    await flushPromises()

    // Felder befüllen
    await w.find('#pm-name').setValue('Mein Testprofil')
    await w.find('#pm-base-url').setValue('http://localhost:11434/v1')
    await w.find('#pm-model').setValue('llama3:8b')

    // Speichern klicken (stubActions: true → create ist bereits ein vi.fn spy)
    const saveBtn = w.findAll('button.v4-btn--primary').find(b => b.text() === 'Speichern')
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(store.create).toHaveBeenCalledWith({
      name: 'Mein Testprofil',
      provider: 'ollama',
      base_url: 'http://localhost:11434/v1',
      model_name: 'llama3:8b',
      api_key: null,
      is_default: false,
    })
  })

  it('store.setDefault wird beim Klick auf "Als Standard setzen" aufgerufen', async () => {
    const w = wrap()
    await flushPromises()

    const { useLlmProfilesStore } = await import('@/store/llmProfiles')
    const store = useLlmProfilesStore()

    // "Als Standard setzen" ist für PROFILE_B (p2) aktiv (p1 ist schon default)
    const setDefaultBtns = w.findAll('button').filter(b => b.text() === 'Als Standard setzen')
    // p1 ist deaktiviert (is_default=true), p2 ist aktiv
    // @vue/test-utils gibt für disabled="" den leeren String, nicht undefined.
    const activeBtn = setDefaultBtns.find(b => b.attributes('disabled') === undefined)
    await activeBtn!.trigger('click')
    await flushPromises()

    // stubActions: true → setDefault ist bereits ein vi.fn spy
    expect(store.setDefault).toHaveBeenCalledWith('p2')
  })
})
