/**
 * Tests fuer `WorkspaceLlmRoutingDefaultsResponseSchema`.
 *
 * Regression: Das Backend reichert JEDE `/api/llm/routing/defaults*`-Antwort
 * via `_with_ai_route()` (backend/app/api/llm_routing.py) um einen
 * aufgelösten Top-Level-`ai_route`-Block an. Das Response-Schema muss diese
 * additive Anreicherung akzeptieren, ohne den restlichen `.strict()`-Vertrag
 * (unbekannte Top-Level-Keys weiterhin ablehnen) aufzuweichen.
 */
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

const validBase = {
  global_default: globalDefault,
  stage_overrides: {},
  updated_at: '2026-07-18T01:08:56.061467Z',
  version: 1,
}

const validAiRoute = {
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

describe('WorkspaceLlmRoutingDefaultsResponseSchema', () => {
  it('parses a bare payload without the ai_route enrichment', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse(validBase)
    expect(result.success).toBe(true)
  })

  it('parses the ai_route-enriched payload emitted by _with_ai_route()', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...validBase,
      ai_route: validAiRoute,
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.ai_route?.source).toBe('workspace')
    }
  })

  it('accepts a minimal ai_route that only carries the required source field', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...validBase,
      ai_route: { source: 'default' },
    })
    expect(result.success).toBe(true)
  })

  it('rejects a payload whose ai_route block violates the AiRoute contract', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...validBase,
      ai_route: { source: 'not-a-real-source' },
    })
    expect(result.success).toBe(false)
  })

  it('rejects provider_fallback ai_route enrichment without a fallback_reason', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...validBase,
      ai_route: { ...validAiRoute, source: 'provider_fallback', fallback_reason: null },
    })
    expect(result.success).toBe(false)
  })

  it('still rejects unrecognized top-level keys other than ai_route (stays strict)', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...validBase,
      unexpected_field: 'should not be accepted',
    })
    expect(result.success).toBe(false)
  })

  it('still enforces the inherited base-contract validations (missing global_default)', () => {
    const { global_default, ...withoutGlobalDefault } = validBase
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse(withoutGlobalDefault)
    expect(result.success).toBe(false)
  })

  it('applies the same defaults as the base schema when optional fields are omitted', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      global_default: globalDefault,
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.stage_overrides).toEqual({})
      expect(result.data.version).toBe(1)
      expect(result.data.ai_route).toBeUndefined()
    }
  })

  it('remains a superset of the store contract: anything valid for the base schema is valid here', () => {
    const baseResult = WorkspaceLlmRoutingDefaultsSchema.safeParse(validBase)
    expect(baseResult.success).toBe(true)
    const responseResult = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse(validBase)
    expect(responseResult.success).toBe(true)
  })
})