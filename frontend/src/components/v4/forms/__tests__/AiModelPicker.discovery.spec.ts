import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const discovery = vi.hoisted(() => ({
  models: { value: [] as any[] }, loading: { value: false }, error: { value: null as string | null }, refresh: vi.fn(),
}))

vi.mock('@/composables/useAvailableModels', () => ({
  useAvailableModels: () => discovery,
}))

import AiModelPicker from '../AiModelPicker.vue'

const discoveredModels = [
  { provider_connection_id: 'conn-local', provider_kind: 'ollama', display_name: 'Ollama lokal', model_id: 'qwen3', context_window: 32768, capabilities: ['chat', 'streaming'], status: 'available', local_or_cloud: 'local' },
  { provider_connection_id: 'conn-offline', provider_kind: 'openai', display_name: 'Cloud AI', model_id: 'gpt-offline', context_window: null, capabilities: ['chat'], status: 'unavailable', local_or_cloud: 'cloud' },
  { provider_connection_id: 'conn-embedding', provider_kind: 'openai', display_name: 'Cloud AI', model_id: 'embed-3', context_window: null, capabilities: ['embeddings'], status: 'available', local_or_cloud: 'cloud' },
]

async function mountPicker(props: Record<string, unknown> = {}) {
  discovery.models.value = discoveredModels
  discovery.loading.value = false
  discovery.error.value = null
  discovery.refresh.mockReset().mockResolvedValue(undefined)
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: { aiModelPicker: { placeholder: 'Modell wählen', searchPlaceholder: 'Modell suchen', empty: 'Leer' } } } })
  const wrapper = mount(AiModelPicker, { props, global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('AiModelPicker — Discovery-Daten (Slice 5.2)', () => {
  it('verwendet die ProviderConnection-Discovery statt eingebauter Mock-Daten', async () => {
    const wrapper = await mountPicker()
    const exposed = wrapper.vm as any
    expect(exposed.filteredOptions.map((model: any) => model.model_id)).toEqual(['gpt-offline', 'qwen3'])
  })

  it('konsolidiert mode und capabilityFilter auf denselben Discovery-Datenpfad', async () => {
    const wrapper = await mountPicker({ capabilityFilter: 'streaming' })
    const exposed = wrapper.vm as any
    expect(exposed.filteredOptions.map((model: any) => model.model_id)).toEqual(['qwen3'])
  })

  it('lässt unavailable Provider sichtbar und deaktiviert deren Modell', async () => {
    const wrapper = await mountPicker()
    const exposed = wrapper.vm as any
    const offline = exposed.filteredOptions.find((model: any) => model.model_id === 'gpt-offline')
    expect(offline.status).toBe('unavailable')
    expect(exposed.isDisabled(offline)).toBe(true)
  })

  it('stellt den Discovery-Refresh über die Komponente bereit', async () => {
    const wrapper = await mountPicker()
    const exposed = wrapper.vm as any
    await exposed.refresh()
    expect(discovery.refresh).toHaveBeenCalledWith({ force: true })
  })
})
