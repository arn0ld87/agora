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
