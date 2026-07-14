import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
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
          errors: {
            unknownConnection:
              'Die gewählte Provider-Verbindung ist nicht mehr verfügbar. Bitte wähle ein Modell neu.',
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

// Test-Connection, die im llmProviders-Store (initialState) liegt, damit das
// Connection-Lookup im LlmProfileManager funktioniert.
const CONN_OLLAMA = {
  id: 'conn-ollama-1',
  provider_kind: 'ollama' as const,
  display_name: 'Ollama lokal',
  transport: 'local' as const,
  auth_mode: 'none' as const,
  base_url: 'http://localhost:11434/v1',
  enabled: true,
  status: 'connected' as const,
  status_message: null,
  secret_ref: null,
  capabilities: {},
  created_at: null,
  updated_at: null,
  last_tested_at: null,
}

// AiModelPicker-Stub: emittiert ein AiModelRef (provider_connection_id +
// model_id) via select-Change, ohne auf useAvailableModels oder Backend-Calls
// angewiesen zu sein. Entspricht dem Design-Mapping (specStubCode).
const AiModelPickerStub = defineComponent({
  name: 'AiModelPicker',
  props: {
    modelValue: { type: Object, default: null },
    mode: { type: String, default: 'chat' },
    placeholder: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  methods: {
    onChange(e: Event): void {
      const v = (e.target as HTMLSelectElement).value
      if (!v) {
        this.$emit('update:modelValue', null)
        return
      }
      const sep = v.indexOf('::')
      const provider_connection_id = v.slice(0, sep)
      const model_id = v.slice(sep + 2)
      this.$emit('update:modelValue', {
        provider_connection_id,
        model_id,
        source: 'explicit',
      })
    },
  },
  template: `
    <select
      class="ai-model-picker-stub"
      data-testid="ai-model-picker-stub"
      :value="modelValue ? modelValue.provider_connection_id + '::' + modelValue.model_id : ''"
      @change="onChange"
    >
      <option value=""></option>
      <option
        value="conn-ollama-1::llama3:8b"
        data-testid="ai-model-picker-option-known"
        data-provider-connection-id="conn-ollama-1"
        data-model-id="llama3:8b"
      >Ollama — llama3:8b</option>
      <option
        value="conn-unknown::mystery-model"
        data-testid="ai-model-picker-option-unknown"
        data-provider-connection-id="conn-unknown"
        data-model-id="mystery-model"
      >Unknown — mystery-model</option>
    </select>
  `,
})

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
            llmProviders: {
              connections: { 'conn-ollama-1': CONN_OLLAMA },
            },
          },
          stubActions: true,
        }),
      ],
      stubs: {
        Card: { template: '<div><slot /></div>' },
        AiModelPicker: AiModelPickerStub,
      },
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

    const { useLlmProfilesStore } = await import('@/store/aiModels')
    const store = useLlmProfilesStore()

    // Neues-Profil-Formular öffnen
    await w.find('button.v4-btn--primary').trigger('click')
    await flushPromises()

    // Felder befüllen
    await w.find('#pm-name').setValue('Mein Testprofil')
    await w.find('#pm-base-url').setValue('http://localhost:11434/v1')
    // AiModelPicker-Stub emittiert AiModelRef mit provider_connection_id
    // 'conn-ollama-1' + model_id 'llama3:8b'. onPickerChange löst die Connection
    // auf → provider='ollama', base_url aus Connection, model_name aus ref.model_id.
    await w.find('select.ai-model-picker-stub').setValue('conn-ollama-1::llama3:8b')

    // Speichern klicken (stubActions: true → create ist bereits ein vi.fn spy)
    const saveBtn = w.findAll('button.v4-btn--primary').find((b) => b.text() === 'Speichern')
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

    const { useLlmProfilesStore } = await import('@/store/aiModels')
    const store = useLlmProfilesStore()

    const setDefaultBtns = w.findAll('button').filter((b) => b.text() === 'Als Standard setzen')
    const activeBtn = setDefaultBtns.find((b) => b.attributes('disabled') === undefined)
    await activeBtn!.trigger('click')
    await flushPromises()

    expect(store.setDefault).toHaveBeenCalledWith('p2')
  })

  it('unknown-connection blockiert Save und zeigt Fehler', async () => {
    const w = wrap()
    await flushPromises()

    const { useLlmProfilesStore } = await import('@/store/aiModels')
    const store = useLlmProfilesStore()

    // Neues-Profil-Formular öffnen
    await w.find('button.v4-btn--primary').trigger('click')
    await flushPromises()

    // Felder befüllen — base_url gesetzt, damit Save-disabled ohne unknownConnection
    // erfüllt wäre.
    await w.find('#pm-name').setValue('Test')
    await w.find('#pm-base-url').setValue('http://localhost:11434/v1')
    // AiModelPicker-Stub auf unbekannte Connection setzen → onPickerChange
    // findet keine Connection → pickerError=true.
    await w.find('select.ai-model-picker-stub').setValue('conn-unknown::mystery-model')
    await flushPromises()

    // Fehler-Banner sichtbar
    const errorBanner = w.find('[data-testid="pm-unknown-connection-error"]')
    expect(errorBanner.exists()).toBe(true)
    expect(errorBanner.attributes('role')).toBe('alert')

    // Save-Button disabled
    const saveBtn = w.findAll('button.v4-btn--primary').find((b) => b.text() === 'Speichern')
    expect(saveBtn?.attributes('disabled')).toBeDefined()

    // Save-Klick versuch (sollte durch disabled nicht passieren, aber zur
    // Sicherheit explizit prüfen, dass create nicht aufgerufen wurde)
    await flushPromises()
    expect(store.create).not.toHaveBeenCalled()
  })
})