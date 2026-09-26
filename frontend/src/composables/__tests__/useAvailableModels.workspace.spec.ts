import { beforeEach, describe, expect, it, vi } from 'vitest'

const operator = vi.hoisted(() => ({ value: false }))
const providers = vi.hoisted(() => ({ loadConnections: vi.fn(), fetchConnectionModels: vi.fn() }))
const workspace = vi.hoisted(() => ({ listWorkspaceAvailableModels: vi.fn() }))

vi.mock('@/composables/useOperatorAccess', () => ({ useOperatorAccess: () => operator }))
vi.mock('@/store/aiModels', () => ({ useLlmProvidersStore: () => providers }))
vi.mock('@/api/workspaceAvailableModels', () => workspace)

import { useAvailableModels } from '../useAvailableModels'

describe('useAvailableModels — JWT workspace discovery', () => {
  beforeEach(() => {
    operator.value = false
    providers.loadConnections.mockReset()
    providers.fetchConnectionModels.mockReset()
    workspace.listWorkspaceAvailableModels.mockReset().mockResolvedValue({
      items: [{
        provider_connection_id: 'openai', provider_kind: 'openai', display_name: 'OpenAI',
        model_id: 'gpt-4o', model_label: 'GPT-4o', source: 'live', status: 'available',
        local_or_cloud: 'cloud', capabilities: ['chat'], unsupported_capabilities: [],
      }],
      total: 1,
      providers: [{ provider_connection_id: 'openai', provider_kind: 'openai', display_name: 'OpenAI' }],
    })
  })

  it('lädt nur JWT-sichere Workspace-Modelle und keine Betreiber-Connections', async () => {
    const { models } = useAvailableModels()
    await vi.waitFor(() => expect(models.value).toHaveLength(1))
    expect(models.value[0]).toMatchObject({ provider_connection_id: 'openai', model_id: 'gpt-4o' })
    expect(providers.loadConnections).not.toHaveBeenCalled()
    expect(providers.fetchConnectionModels).not.toHaveBeenCalled()
  })

  it('zeigt einen strukturierten Fehler bei ungültiger Workspace-Antwort', async () => {
    workspace.listWorkspaceAvailableModels.mockRejectedValue(new Error('Invalid workspace model response'))
    const { models, error } = useAvailableModels()
    await vi.waitFor(() => expect(error.value).toBe('Invalid workspace model response'))
    expect(models.value).toEqual([])
  })
})
