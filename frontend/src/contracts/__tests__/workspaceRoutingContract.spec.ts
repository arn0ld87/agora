import { describe, expect, it } from 'vitest'

import {
  WorkspaceLlmRoutingDefaultsResponseSchema,
  WorkspaceLlmRoutingDefaultsSchema,
} from '../workspaceRoutingContract'

const globalDefault = {
  provider_id: 'openai',
  model: 'gpt-5.4-nano',
  reasoning_effort: 'none' as const,
  provider_options: {},
}

// Minimal fixture for the ai_route enrichment, cf. `_with_ai_route()` in
// backend/app/api/llm_routing.py. `source` is the only field on AiRouteSchema
// without a default.
const aiRoute = {
  stage: null,
  provider_connection_id: 'openai',
  model_id: 'gpt-5.4-nano',
  source: 'workspace' as const,
  validated_capabilities: {},
  provider_options: {},
  routing_version: 1,
  resolved_at: null,
  fallback_reason: null,
}

const validPayload = {
  global_default: globalDefault,
  stage_overrides: {},
  updated_at: '2026-07-18T01:08:56.061467Z',
  version: 1,
}

describe('WorkspaceLlmRoutingDefaultsSchema (store contract)', () => {
  it('accepts a minimal payload and applies defaults', () => {
    const result = WorkspaceLlmRoutingDefaultsSchema.safeParse({ global_default: {} })

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.stage_overrides).toEqual({})
      expect(result.data.version).toBe(1)
    }
  })

  it('accepts stage overrides keyed by a known stage id', () => {
    expect(
      WorkspaceLlmRoutingDefaultsSchema.safeParse({
        global_default: globalDefault,
        stage_overrides: { ontology_generation: globalDefault },
      }).success,
    ).toBe(true)
  })

  it('rejects an unknown stage id in stage_overrides', () => {
    expect(
      WorkspaceLlmRoutingDefaultsSchema.safeParse({
        global_default: globalDefault,
        stage_overrides: { not_a_real_stage: globalDefault },
      }).success,
    ).toBe(false)
  })

  it('rejects the ai_route enrichment on the strict store contract', () => {
    // The store contract stays strict on purpose: `ai_route` is a response-
    // only enrichment and must never round-trip back into persisted state.
    expect(
      WorkspaceLlmRoutingDefaultsSchema.safeParse({
        ...validPayload,
        ai_route: aiRoute,
      }).success,
    ).toBe(false)
  })

  it('rejects an unrelated unrecognized top-level key', () => {
    expect(
      WorkspaceLlmRoutingDefaultsSchema.safeParse({
        ...validPayload,
        unexpected_field: true,
      }).success,
    ).toBe(false)
  })

  it('requires global_default', () => {
    expect(
      WorkspaceLlmRoutingDefaultsSchema.safeParse({
        stage_overrides: {},
        version: 1,
      }).success,
    ).toBe(false)
  })
})

describe('WorkspaceLlmRoutingDefaultsResponseSchema (API response contract)', () => {
  it('accepts a payload without the ai_route enrichment (optional field)', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse(validPayload)

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.ai_route).toBeUndefined()
    }
  })

  it('accepts the ai_route-enriched payload emitted by _with_ai_route()', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...validPayload,
      ai_route: aiRoute,
    })

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.ai_route?.source).toBe('workspace')
      expect(result.data.ai_route?.model_id).toBe('gpt-5.4-nano')
    }
  })

  it('rejects a malformed ai_route block (missing required source)', () => {
    const { source: _source, ...aiRouteWithoutSource } = aiRoute

    expect(
      WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
        ...validPayload,
        ai_route: aiRouteWithoutSource,
      }).success,
    ).toBe(false)
  })

  it('rejects an ai_route block with an unrecognized field', () => {
    expect(
      WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
        ...validPayload,
        ai_route: { ...aiRoute, unexpected_ai_route_field: true },
      }).success,
    ).toBe(false)
  })

  it('still rejects unrelated unrecognized top-level keys', () => {
    expect(
      WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
        ...validPayload,
        unexpected_field: true,
      }).success,
    ).toBe(false)
  })

  it('still requires global_default', () => {
    expect(
      WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
        stage_overrides: {},
        version: 1,
        ai_route: aiRoute,
      }).success,
    ).toBe(false)
  })

  it('applies the same defaults as the store schema', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      global_default: {},
    })

    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.stage_overrides).toEqual({})
      expect(result.data.version).toBe(1)
      expect(result.data.ai_route).toBeUndefined()
    }
  })

  it('rejects an unknown stage id in stage_overrides (inherited from the store schema)', () => {
    expect(
      WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
        global_default: globalDefault,
        stage_overrides: { not_a_real_stage: globalDefault },
      }).success,
    ).toBe(false)
  })
})