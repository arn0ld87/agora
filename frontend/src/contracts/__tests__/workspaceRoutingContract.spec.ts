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

const baseDefaults = {
  global_default: globalDefault,
  stage_overrides: {},
  updated_at: '2026-07-18T01:08:56.061467Z',
  version: 1,
}

describe('WorkspaceLlmRoutingDefaultsSchema', () => {
  it('parses a well-formed defaults payload', () => {
    const result = WorkspaceLlmRoutingDefaultsSchema.safeParse(baseDefaults)
    expect(result.success).toBe(true)
  })

  it('rejects an ai_route-enriched payload (strict store contract)', () => {
    const result = WorkspaceLlmRoutingDefaultsSchema.safeParse({
      ...baseDefaults,
      ai_route: aiRoute,
    })
    expect(result.success).toBe(false)
  })

  it('rejects unrecognized top-level keys', () => {
    const result = WorkspaceLlmRoutingDefaultsSchema.safeParse({
      ...baseDefaults,
      unexpected: true,
    })
    expect(result.success).toBe(false)
  })

  it('defaults stage_overrides and version when omitted', () => {
    const result = WorkspaceLlmRoutingDefaultsSchema.parse({
      global_default: globalDefault,
    })
    expect(result.stage_overrides).toEqual({})
    expect(result.version).toBe(1)
  })
})

describe('WorkspaceLlmRoutingDefaultsResponseSchema — ai_route enrichment (regression)', () => {
  it('accepts the backend-enriched payload with a top-level ai_route block', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...baseDefaults,
      ai_route: aiRoute,
    })
    expect(result.success).toBe(true)
    expect(result.data?.ai_route).toEqual(aiRoute)
  })

  it('still accepts a payload without ai_route (field is optional)', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse(baseDefaults)
    expect(result.success).toBe(true)
    expect(result.data?.ai_route).toBeUndefined()
  })

  it('rejects an ai_route block that fails AiRouteSchema validation', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...baseDefaults,
      ai_route: { ...aiRoute, source: undefined },
    })
    expect(result.success).toBe(false)
  })

  it('rejects an ai_route block with a provider_fallback source and no reason', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...baseDefaults,
      ai_route: { ...aiRoute, source: 'provider_fallback', fallback_reason: null },
    })
    expect(result.success).toBe(false)
  })

  it('still rejects unrelated unrecognized top-level keys', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ...baseDefaults,
      ai_route: aiRoute,
      unexpected: true,
    })
    expect(result.success).toBe(false)
  })

  it('still requires the base fields (global_default is mandatory)', () => {
    const result = WorkspaceLlmRoutingDefaultsResponseSchema.safeParse({
      ai_route: aiRoute,
    })
    expect(result.success).toBe(false)
  })
})