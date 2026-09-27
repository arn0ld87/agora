import { describe, expect, it } from 'vitest'
import { WorkspaceAvailableModelsListSchema } from '../workspaceAvailableModelsContract'

const provider = { provider_connection_id: 'minimax', provider_kind: 'minimax', display_name: 'MiniMax' }

describe('WorkspaceAvailableModelsListSchema', () => {
  it('akzeptiert einen konfigurierten Anbieter ohne Discovery-Ergebnisse', () => {
    expect(WorkspaceAvailableModelsListSchema.safeParse({
      items: [], providers: [provider], total: 0,
    }).success).toBe(true)
  })

  it('übernimmt unbekannte Fähigkeiten als Backend-Strings und weist inkonsistente Zähler zurück', () => {
    const item = {
      ...provider, model_id: 'MiniMax-M2.5', model_label: 'MiniMax M2.5',
      source: 'live', status: 'available', local_or_cloud: 'cloud',
      capabilities: ['secret_disclosure'], unsupported_capabilities: [],
    }
    expect(WorkspaceAvailableModelsListSchema.safeParse({
      items: [item], providers: [provider], total: 1,
    }).success).toBe(true)
    expect(WorkspaceAvailableModelsListSchema.safeParse({
      items: [{ ...item, capabilities: ['chat'] }], providers: [provider], total: 0,
    }).success).toBe(false)
  })
})
