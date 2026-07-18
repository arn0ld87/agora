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

describe('llmRoutingDefaults api client — Request-Wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const envelope = {
    data: {
      global_default: globalDefault,
      stage_overrides: {},
      version: 1,
    },
  }

  it('getRoutingDefaults ruft GET /api/llm/routing/defaults ohne Body auf', async () => {
    serviceMock.get.mockResolvedValueOnce(envelope)

    await getRoutingDefaults()

    expect(serviceMock.get).toHaveBeenCalledTimes(1)
    expect(serviceMock.get).toHaveBeenCalledWith('/api/llm/routing/defaults')
  })

  it('replaceRoutingDefaults sendet PUT /api/llm/routing/defaults mit dem vollen Payload', async () => {
    serviceMock.put.mockResolvedValueOnce(envelope)
    const payload = { global_default: globalDefault, stage_overrides: {}, version: 1 }

    await replaceRoutingDefaults(payload)

    expect(serviceMock.put).toHaveBeenCalledWith('/api/llm/routing/defaults', payload)
  })

  it('replaceGlobalDefault sendet PUT /api/llm/routing/defaults/global mit der Route', async () => {
    serviceMock.put.mockResolvedValueOnce(envelope)

    await replaceGlobalDefault(globalDefault)

    expect(serviceMock.put).toHaveBeenCalledWith(
      '/api/llm/routing/defaults/global',
      globalDefault,
    )
  })

  it('patchRoutingDefaultStage sendet PATCH mit der Route als Body, wenn eine Route übergeben wird', async () => {
    serviceMock.patch.mockResolvedValueOnce(envelope)

    await patchRoutingDefaultStage('ontology_generation', globalDefault)

    expect(serviceMock.patch).toHaveBeenCalledWith(
      '/api/llm/routing/defaults/stages/ontology_generation',
      globalDefault,
    )
  })

  it('patchRoutingDefaultStage sendet { clear: true }, wenn route === null (Stage-Override löschen)', async () => {
    serviceMock.patch.mockResolvedValueOnce(envelope)

    await patchRoutingDefaultStage('ontology_generation', null)

    expect(serviceMock.patch).toHaveBeenCalledWith(
      '/api/llm/routing/defaults/stages/ontology_generation',
      { clear: true },
    )
  })
})

describe('llmRoutingDefaults api client — Response-Schema-Validierung', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('akzeptiert eine Antwort ohne ai_route-Feld (optional, kein enrichment nötig)', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
      },
    })

    const result = await getRoutingDefaults()

    expect(result.ai_route).toBeUndefined()
    expect(result.global_default).toMatchObject({ model: 'gpt-5.4-nano' })
  })

  it('lehnt eine Antwort ohne global_default mit "schema mismatch" ab', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: { stage_overrides: {}, version: 1 },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/)
  })

  it('lehnt eine Antwort mit einem fehlerhaften ai_route-Block ab (source fehlt)', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
        ai_route: { ...aiRoute, source: undefined },
      },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/)
  })

  it('lehnt weiterhin unbekannte Top-Level-Felder außerhalb von ai_route ab', async () => {
    serviceMock.get.mockResolvedValueOnce({
      data: {
        global_default: globalDefault,
        stage_overrides: {},
        version: 1,
        unexpected_field: true,
      },
    })

    await expect(getRoutingDefaults()).rejects.toThrow(/schema mismatch/)
  })

  it('gibt den ai_route-Block unverändert an den Aufrufer durch, wenn er vorhanden ist', async () => {
    serviceMock.put.mockResolvedValueOnce(enrichedEnvelope)

    const result = await replaceGlobalDefault(globalDefault)

    expect(result.ai_route).toMatchObject({
      source: 'workspace',
      model_id: 'gpt-5.4-nano',
    })
  })
})
