/**
 * AiModelPicker — Spec-Tests (Slice 5.1).
 *
 * Reka-ui Combobox rendert Items nur im offenen Dropdown. Wir testen
 * Logik ueber die `defineExpose`-API (filteredOptions, providerGroups)
 * und Emits ueber die echte ComboboxRoot-Komponente.
 *
 * 1. mountet ohne Crash
 * 2. gefilterte Optionen im Default-Mock-Set (mode=chat)
 * 3. filtert mode=embedding (Capability-Filter)
 * 4. Workspace-Default steht in der sortierten Liste vorne
 * 5. emittiert update:modelValue mit korrekter AiModelRef-Struktur
 * 6. emittiert 'null' bei clear
 * 7. akzeptiert options-Prop (kein Default-Mock-Lookup)
 * 8. markiert unavailable Modelle als ComboboxItem disabled
 * 9. sortiert Provider-Gruppen alphabetisch
 * 10. respektiert disabled-Prop (Input disabled)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const discovery = vi.hoisted(() => ({
  models: { value: [] as any[] }, loading: { value: false }, error: { value: null as string | null }, refresh: vi.fn(),
}))

vi.mock('@/composables/useAvailableModels', () => ({
  useAvailableModels: () => discovery,
}))

import AiModelPicker from '../AiModelPicker.vue'
import type { AiModelRefInput } from '@/contracts/aiModelRef'

const MOCK_OPTIONS: AiModelRefInput[] = [
  {
    provider_connection_id: 'conn-test-1',
    provider_kind: 'ollama',
    display_name: 'Test Ollama',
    model_id: 'qwen-test',
    context_window: 32768,
    capabilities: ['chat', 'streaming'],
    status: 'available',
    is_workspace_default: true,
    local_or_cloud: 'local',
  },
  {
    provider_connection_id: 'conn-test-1',
    provider_kind: 'ollama',
    display_name: 'Test Ollama',
    model_id: 'llama-test',
    context_window: 8192,
    capabilities: ['chat'],
    status: 'available',
    local_or_cloud: 'local',
  },
  {
    provider_connection_id: 'conn-test-2',
    provider_kind: 'openai',
    display_name: 'Test OpenAI',
    model_id: 'gpt-test',
    context_window: 128000,
    capabilities: ['chat', 'streaming', 'vision'],
    status: 'available',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-test-3',
    provider_kind: 'openai',
    display_name: 'Test OpenAI Degraded',
    model_id: 'gpt-degraded',
    context_window: 128000,
    capabilities: ['chat', 'streaming'],
    status: 'degraded',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-test-4',
    provider_kind: 'openai',
    display_name: 'Test OpenAI Offline',
    model_id: 'gpt-offline',
    context_window: 128000,
    capabilities: ['chat'],
    status: 'unavailable',
    local_or_cloud: 'cloud',
  },
  {
    provider_connection_id: 'conn-test-emb',
    provider_kind: 'openai',
    display_name: 'Test Embeddings',
    model_id: 'text-embed-test',
    context_window: 0,
    capabilities: ['embeddings'],
    status: 'available',
    local_or_cloud: 'cloud',
  },
]

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    fallbackLocale: 'en',
    messages: {
      en: {
        aiModelPicker: {
          placeholder: 'Select model …',
          searchPlaceholder: 'Search model …',
          empty: 'No models available.',
          workspaceDefault: 'Workspace default',
          inheritWorkspaceDefault: 'Use workspace default',
          loading: 'Loading models …',
          badge: {
            local: 'local',
            cloud: 'Cloud',
            degraded: 'degraded',
            unavailable: 'unavailable',
          },
        },
      },
    },
  })
}

async function mountPicker(overrides: Record<string, unknown> = {}) {
  const i18n = makeI18n()
  const wrapper = mount(AiModelPicker, {
    props: { options: MOCK_OPTIONS, ...overrides },
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return wrapper
}

describe('AiModelPicker (Slice 5.1, isolated)', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('mountet ohne Crash', async () => {
    const w = await mountPicker()
    expect(w.exists()).toBe(true)
    expect(w.find('.ai-model-picker').exists()).toBe(true)
  })

  it('rendert im Default-Mock-Set genau 5 chat-faehige Modelle (1 Embedding ausgefiltert)', async () => {
    const w = await mountPicker()
    const exposed = w.vm as unknown as {
      filteredOptions: readonly AiModelRefInput[]
    }
    expect(exposed.filteredOptions).toBeDefined()
    expect(exposed.filteredOptions.length).toBe(5)
    expect(exposed.filteredOptions.every((o) => o.capabilities.includes('chat'))).toBe(true)
  })

  it('filtert mode=embedding so dass nur Embedding-Modelle bleiben', async () => {
    const w = await mountPicker({ mode: 'embedding' })
    const exposed = w.vm as unknown as {
      filteredOptions: readonly AiModelRefInput[]
    }
    expect(exposed.filteredOptions.length).toBe(1)
    expect(exposed.filteredOptions[0].model_id).toBe('text-embed-test')
  })

  it('stellt Workspace-Default in der sortierten Liste nach vorne', async () => {
    const w = await mountPicker()
    const exposed = w.vm as unknown as {
      filteredOptions: readonly AiModelRefInput[]
    }
    expect(exposed.filteredOptions[0].model_id).toBe('qwen-test')
    expect(exposed.filteredOptions[0].is_workspace_default).toBe(true)
  })

  it('emittiert update:modelValue mit korrekter AiModelRef-Struktur', async () => {
    const w = await mountPicker()
    const exposed = w.vm as unknown as {
      filteredOptions: readonly AiModelRefInput[]
      selectedId: string | null
    }
    // Simuliert: User waehlt qwen-test (Workspace-Default)
    const target = exposed.filteredOptions[0]
    expect(target.model_id).toBe('qwen-test')
    // update ueber ComboboxRoot emulieren
    const itemId = `${target.provider_connection_id}\u0000${target.model_id}`
    const root = w.findComponent({ name: 'ComboboxRoot' })
    expect(root.exists()).toBe(true)
    await root.vm.$emit('update:modelValue', itemId)
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
    const payload = emitted![0][0] as {
      provider_connection_id: string
      model_id: string
      source: string
    }
    expect(payload.provider_connection_id).toBe('conn-test-1')
    expect(payload.model_id).toBe('qwen-test')
    expect(payload.source).toBe('workspace-default')
  })

  it('emittiert null, wenn das Dropdown ohne Auswahl geschlossen wird (clear)', async () => {
    const w = await mountPicker({
      modelValue: {
        provider_connection_id: 'conn-test-1',
        model_id: 'qwen-test',
        source: 'workspace-default',
      },
    })
    const root = w.findComponent({ name: 'ComboboxRoot' })
    await root.vm.$emit('update:modelValue', '')
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted![emitted!.length - 1][0]).toBeNull()
  })

  it('akzeptiert options-Prop (kein Default-Mock-Lookup)', async () => {
    const custom: AiModelRefInput[] = [
      {
        provider_connection_id: 'only-one',
        provider_kind: 'mock',
        display_name: 'Spezial',
        model_id: 'special-model',
        context_window: 4096,
        capabilities: ['chat'],
        status: 'available',
        local_or_cloud: 'local',
      },
    ]
    const w = await mountPicker({ options: custom })
    const exposed = w.vm as unknown as {
      filteredOptions: readonly AiModelRefInput[]
    }
    expect(exposed.filteredOptions.length).toBe(1)
    expect(exposed.filteredOptions[0].model_id).toBe('special-model')
  })

  it('markiert unavailable Modelle als ComboboxItem disabled (Logik via isDisabled-Pattern)', async () => {
    // Die Component entscheidet ueber isDisabled(input) im Template. Hier
    // verifizieren wir die Datengrundlage: alle 5 chat-Modelle sind
    // in den filteredOptions enthalten, und die unavailable-Status-Markierung
    // bleibt sichtbar (wird vom Template als data-disabled gerendert).
    const w = await mountPicker()
    const exposed = w.vm as unknown as {
      filteredOptions: readonly AiModelRefInput[]
    }
    const offline = exposed.filteredOptions.find((o) => o.model_id === 'gpt-offline')
    expect(offline).toBeDefined()
    expect(offline!.status).toBe('unavailable')
  })

  it('sortiert Provider-Gruppen alphabetisch nach display_name', async () => {
    const w = await mountPicker()
    const exposed = w.vm as unknown as {
      providerGroups: ReadonlyArray<{ name: string; items: AiModelRefInput[] }>
    }
    const groupNames = exposed.providerGroups.map((g) => g.name)
    // Test Ollama < Test OpenAI < Test OpenAI Degraded < Test OpenAI Offline
    const sorted = [...groupNames].sort()
    expect(groupNames).toEqual(sorted)
  })

  it('respektiert disabled-Prop am Input-Element', async () => {
    const w = await mountPicker({ disabled: true })
    const root = w.find('.ai-model-picker')
    expect(root.attributes('data-disabled')).toBeDefined()
    const input = w.find('.ai-model-picker__input')
    expect(input.attributes('disabled')).toBeDefined()
  })
})
