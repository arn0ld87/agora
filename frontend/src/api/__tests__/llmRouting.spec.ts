import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
}))

import {
  getRunLlmRouting,
  listLlmProviders,
  listProviderModels,
  patchStageLlmRouting,
  updateRunLlmRouting,
} from '../llmRouting'

describe('llmRouting api client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('nutzt die Backend-/api-Pfade fuer Provider und Modelle', async () => {
    serviceMock.get.mockResolvedValueOnce({ data: [{ id: 'openai' }] })
    serviceMock.get.mockResolvedValueOnce({ data: [{ id: 'gpt-5.5', name: 'gpt-5.5' }] })

    await expect(listLlmProviders()).resolves.toEqual([{ id: 'openai' }])
    await expect(listProviderModels('openai', 'https://api.openai.com/v1')).resolves.toEqual([
      { id: 'gpt-5.5', name: 'gpt-5.5' },
    ])

    expect(serviceMock.get).toHaveBeenNthCalledWith(1, '/api/llm/providers')
    expect(serviceMock.get).toHaveBeenNthCalledWith(
      2,
      '/api/llm/providers/openai/models?base_url=https%3A%2F%2Fapi.openai.com%2Fv1',
    )
  })

  it('nutzt die Backend-/api-Pfade fuer Run-Routing-Saves', async () => {
    const routing = {
      global_default: {
        provider_id: 'openai',
        model: 'gpt-5.5',
        reasoning_effort: 'medium' as const,
        provider_options: {},
      },
      stage_overrides: {},
      routing_version: 1,
    }
    const stageRoute = {
      provider_id: 'openai',
      model: 'gpt-5.5-mini',
      reasoning_effort: 'low' as const,
      provider_options: {},
    }
    serviceMock.get.mockResolvedValueOnce({
      data: { runtime_config: routing, snapshots: {}, invocation_events: [] },
    })
    serviceMock.put.mockResolvedValueOnce({ data: { ...routing, routing_version: 2 } })
    serviceMock.patch.mockResolvedValueOnce({ data: { ...routing, routing_version: 3 } })

    await expect(getRunLlmRouting('run_123')).resolves.toEqual({
      runtime_config: routing,
      snapshots: {},
      invocation_events: [],
    })
    await expect(updateRunLlmRouting('run_123', routing)).resolves.toMatchObject({
      routing_version: 2,
    })
    await expect(patchStageLlmRouting('run_123', 'graph_build', stageRoute)).resolves.toMatchObject({
      routing_version: 3,
    })

    expect(serviceMock.get).toHaveBeenCalledWith('/api/runs/run_123/llm-routing')
    expect(serviceMock.put).toHaveBeenCalledWith('/api/runs/run_123/llm-routing', routing)
    expect(serviceMock.patch).toHaveBeenCalledWith(
      '/api/runs/run_123/llm-routing/stages/graph_build',
      stageRoute,
    )
  })
})
