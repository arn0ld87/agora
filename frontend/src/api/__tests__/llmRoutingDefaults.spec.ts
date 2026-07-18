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
})

describe('llmRoutingDefaults api client — Pfade und Payloads', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ruft GET /api/llm/routing/defaults ohne Body auf', async () => {
    serviceMock.get.mockResolvedValueOnce(enrichedEnvelope)

    await getRoutingDefaults()

    expect(serviceMock.get).toHaveBeenCalledWith('/api/llm/routing/defaults')
  })

  it('ruft PUT /api/llm/routing/defaults mit dem vollstaendigen Payload auf', async () => {
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)
    const payload = { global_default: globalDefault, stage_overrides: {}, version: 1 }

    await replaceRoutingDefaults(payload)

    expect(serviceMock.put).toHaveBeenCalledWith('/api/llm/routing/defaults', payload)
  })

  it('ruft PUT /api/llm/routing/defaults/global mit der Route auf', async () => {
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)

    await replaceGlobalDefault(globalDefault)

    expect(serviceMock.put).toHaveBeenCalledWith('/api/llm/routing/defaults/global', globalDefault)
  })

  it('ruft PATCH /api/llm/routing/defaults/stages/:stageId mit der Route auf', async () => {
    serviceMock.patch.mockResolvedValueOnce(enrichedEnvelope)

    await patchRoutingDefaultStage('graph_build', globalDefault)

    expect(serviceMock.patch).toHaveBeenCalledWith(
      '/api/llm/routing/defaults/stages/graph_build',
      globalDefault,
    )
  })

  it('sendet { clear: true } statt eines Route-Body, wenn die Stage-Route null ist', async () => {
    serviceMock.patch.mockResolvedValueOnce(enrichedEnvelope)

    await patchRoutingDefaultStage('graph_build', null)

    expect(serviceMock.patch).toHaveBeenCalledWith('/api/llm/routing/defaults/stages/graph_build', {
      clear: true,
    })
  })
})

describe('llmRoutingDefaults api client — unangereicherte Antworten (Backward-Compat)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const plainEnvelope = {
    data: {
      global_default: globalDefault,
      stage_overrides: {},
      updated_at: '2026-07-18T01:08:56.061467Z',
      version: 1,
    },
  }

  it('parst eine Antwort ohne ai_route weiterhin korrekt', async () => {
    serviceMock.get.mockResolvedValueOnce(plainEnvelope)

    const result = await getRoutingDefaults()

    expect(result).toMatchObject({ version: 1 })
    expect(result.ai_route).toBeUndefined()
  })
})

describe('llmRoutingDefaults api client — Schema-Drift (negativ)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('wirft einen typisierten Fehler, wenn das Backend global_default weglaesst', async () => {
    serviceMock.get.mockResolvedValueOnce({ data: { stage_overrides: {}, version: 1 } })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })

  it('wirft einen typisierten Fehler, wenn ai_route dem AiRoute-Vertrag widerspricht', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
        ai_route: { ...aiRoute, source: 'not-a-real-source' },
      },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })

  it('wirft einen typisierten Fehler bei unbekannten Top-Level-Keys jenseits von ai_route', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
        unexpected_field: 'nope',
      },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/i)
  })
})
