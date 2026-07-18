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
  getRoutingDefaults,
  patchRoutingDefaultStage,
  replaceGlobalDefault,
  replaceRoutingDefaults,
} from '../llmRoutingDefaults'

const globalDefault = {
  provider_id: 'openai',
  model: 'gpt-5.4-nano',
  reasoning_effort: 'none' as const,
  provider_options: {},
}

// Das Backend reichert JEDE routing/defaults-Antwort via `_with_ai_route()`
// (backend/app/api/llm_routing.py) um einen Top-Level-`ai_route`-Key an. Der
// Frontend-Response-Parser muss diese Anreicherung akzeptieren, statt strikt
// mit `unrecognized_keys` abzubrechen (Regression: LlmProvidersView-Crash bei
// Load und beim Speichern des Workspace-Defaults).
const aiRoute = {
  stage: null,
  provider_connection_id: 'openai',
  model_id: 'gpt-5.4-nano',
  source: 'workspace',
  validated_capabilities: {},
  provider_options: {},
  routing_version: 1,
  resolved_at: null,
  fallback_reason: null,
}

const enrichedEnvelope = {
  data: {
    global_default: globalDefault,
    stage_overrides: {},
    updated_at: '2026-07-18T01:08:56.061467Z',
    version: 1,
    ai_route: aiRoute,
  },
}

describe('llmRoutingDefaults api client — ai_route-Anreicherung (Regression)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('parst die ai_route-angereicherte Antwort ohne "schema mismatch"', async () => {
    serviceMock.get.mockResolvedValueOnce(enrichedEnvelope)
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)
    serviceMock.patch.mockResolvedValueOnce(enrichedEnvelope)

    await expect(getRoutingDefaults()).resolves.toMatchObject({
      global_default: { model: 'gpt-5.4-nano' },
    })
    await expect(replaceGlobalDefault(globalDefault)).resolves.toMatchObject({
      version: 1,
    })
    await expect(
      replaceRoutingDefaults({ global_default: globalDefault, stage_overrides: {}, version: 1 }),
    ).resolves.toMatchObject({ version: 1 })
    await expect(
      patchRoutingDefaultStage('ontology_generation', globalDefault),
    ).resolves.toMatchObject({ version: 1 })
  })

  it('calls the expected backend routes with the expected payloads', async () => {
    serviceMock.get.mockResolvedValueOnce(enrichedEnvelope)
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)
    serviceMock.patch.mockResolvedValueOnce(enrichedEnvelope)

    await getRoutingDefaults()
    await replaceGlobalDefault(globalDefault)
    await patchRoutingDefaultStage('ontology_generation', globalDefault)

    expect(serviceMock.get).toHaveBeenCalledWith('/api/llm/routing/defaults')
    expect(serviceMock.put).toHaveBeenCalledWith('/api/llm/routing/defaults/global', globalDefault)
    expect(serviceMock.patch).toHaveBeenCalledWith(
      '/api/llm/routing/defaults/stages/ontology_generation',
      globalDefault,
    )
  })

  it('sends { clear: true } when patching a stage default to null', async () => {
    serviceMock.patch.mockResolvedValueOnce(enrichedEnvelope)

    await patchRoutingDefaultStage('ontology_generation', null)

    expect(serviceMock.patch).toHaveBeenCalledWith(
      '/api/llm/routing/defaults/stages/ontology_generation',
      { clear: true },
    )
  })

  it('calls PUT /api/llm/routing/defaults with the full payload for replaceRoutingDefaults', async () => {
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)
    const payload = { global_default: globalDefault, stage_overrides: {}, version: 1 }

    await replaceRoutingDefaults(payload)

    expect(serviceMock.put).toHaveBeenCalledWith('/api/llm/routing/defaults', payload)
  })

  it('still parses a response without the ai_route enrichment (backward compatible)', async () => {
    const plainEnvelope = {
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        updated_at: '2026-07-18T01:08:56.061467Z',
        version: 1,
      },
    }
    serviceMock.get.mockResolvedValueOnce(plainEnvelope)

    const result = await getRoutingDefaults()
    expect(result.ai_route).toBeUndefined()
    expect(result).toMatchObject({ version: 1, global_default: { model: 'gpt-5.4-nano' } })
  })

  it('rejects with a schema-mismatch error when a non-ai_route key is unrecognized', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
        ai_route: aiRoute,
        unexpected_field: 'boom',
      },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with a schema-mismatch error when ai_route itself is malformed', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
        ai_route: { ...aiRoute, source: 'not_a_valid_source' },
      },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })

  it('rejects with a schema-mismatch error when global_default is missing', async () => {
    serviceMock.get.mockResolvedValueOnce({ data: { stage_overrides: {}, version: 1 } })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })
})
