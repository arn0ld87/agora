import { describe, expect, it, vi, beforeEach } from 'vitest'

const store = vi.hoisted(() => ({
  connections: {} as Record<string, any>,
  connectionModels: {} as Record<string, any[]>,
  connectionUnsupported: {} as Record<string, boolean>,
  loadConnections: vi.fn(),
  fetchConnectionModels: vi.fn(),
}))

vi.mock('@/store/llmProviders', () => ({
  useLlmProvidersStore: () => store,
}))

import { useAvailableModels } from '../useAvailableModels'

const localConnection = {
  id: 'conn-local', provider_kind: 'ollama', display_name: 'Ollama lokal',
  transport: 'local', enabled: true, status: 'connected', capabilities: {},
}
const cloudConnection = {
  id: 'conn-cloud', provider_kind: 'openai', display_name: 'Cloud AI',
  transport: 'http', enabled: true, status: 'disconnected', capabilities: {},
}
const chatModel = {
  provider_connection_id: 'conn-local', model_id: 'qwen3', display_name: 'Qwen 3',
  capabilities: { chat: 'supported', streaming: 'supported', vision: 'unsupported' },
  source: 'live', status: 'available', context_window: 32768, local_or_cloud: 'local',
}
const offlineModel = {
  provider_connection_id: 'conn-cloud', model_id: 'gpt-offline', display_name: 'GPT Offline',
  capabilities: { chat: 'supported', streaming: 'unknown' },
  source: 'cached', status: 'available', context_window: null, local_or_cloud: 'cloud',
}

async function waitForModels(length: number) {
  await vi.waitFor(async () => {
    const { models } = useAvailableModels()
    expect(models.value).toHaveLength(length)
  })
}

describe('useAvailableModels — ProviderConnection-Discovery (Slice 5.2)', () => {
  beforeEach(() => {
    store.connections = { 'conn-local': localConnection, 'conn-cloud': cloudConnection }
    store.connectionModels = {}
    store.connectionUnsupported = {}
    store.loadConnections.mockReset().mockResolvedValue(undefined)
    store.fetchConnectionModels.mockReset().mockImplementation(async (id: string) => {
      const models = id === 'conn-local' ? [chatModel] : [offlineModel]
      store.connectionModels[id] = models
      return models
    })
  })

  it('normalisiert provider_connection_id, capabilities, status und local_or_cloud', async () => {
    const { models } = useAvailableModels()
    await vi.waitFor(() => expect(models.value).toHaveLength(2))
    expect(models.value[0]).toMatchObject({
      provider_connection_id: 'conn-cloud', capabilities: ['chat'], status: 'unavailable', local_or_cloud: 'cloud',
    })
    expect(models.value[1]).toMatchObject({
      provider_connection_id: 'conn-local', capabilities: ['chat', 'streaming'], status: 'available', local_or_cloud: 'local',
    })
  })

  it('lädt Modelle über den kanonischen ProviderConnectionStore', async () => {
    useAvailableModels()
    await vi.waitFor(() => expect(store.fetchConnectionModels).toHaveBeenCalledTimes(2))
    expect(store.loadConnections).toHaveBeenCalledOnce()
  })

  it('markiert eine vom Store als unsupported erkannte Connection getrennt', async () => {
    store.connectionUnsupported = { 'conn-local': true }
    const { models } = useAvailableModels()
    await vi.waitFor(() => expect(models.value).toHaveLength(2))
    expect(models.value.find((model) => model.provider_connection_id === 'conn-local')?.status).toBe('unsupported')
  })

  it('behält Offline-Provider sichtbar, aber unavailable', async () => {
    const { models } = useAvailableModels()
    await vi.waitFor(() => expect(models.value).toHaveLength(2))
    expect(models.value.find((model) => model.model_id === 'gpt-offline')).toMatchObject({ status: 'unavailable' })
  })

  it('respektiert nur als supported bestätigte Capabilities', async () => {
    const { models } = useAvailableModels()
    await vi.waitFor(() => expect(models.value).toHaveLength(2))
    expect(models.value.find((model) => model.model_id === 'qwen3')?.capabilities).not.toContain('vision')
  })

  it('erzwingt bei manuellem Refresh eine neue Discovery', async () => {
    const { refresh } = useAvailableModels()
    await vi.waitFor(() => expect(store.fetchConnectionModels).toHaveBeenCalledTimes(2))
    await refresh({ force: true })
    expect(store.fetchConnectionModels).toHaveBeenCalledTimes(4)
  })
})
