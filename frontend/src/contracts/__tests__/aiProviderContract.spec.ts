import { describe, expect, it } from 'vitest'

import aiModelJsonSchema from '../../../../schemas/ai-model.schema.json'
import aiRouteJsonSchema from '../../../../schemas/ai-route.schema.json'
import providerConnectionJsonSchema from '../../../../schemas/ai-provider-connection.schema.json'
import sharedFixtures from '../../../../schemas/fixtures/ai-provider-contract-fixtures.json'

import {
  AiModelSchema,
  AiRouteSchema,
  ModelCapabilitiesSchema,
  ProviderConnectionSchema,
} from '../aiProviderContract'

describe('canonical AI provider contracts', () => {
  const connectionWithBaseUrl = (base_url: string) => ({
    id: 'provider-1',
    provider_kind: 'openai_compatible',
    display_name: 'Provider',
    transport: 'http',
    auth_mode: 'none',
    base_url,
  })

  it('keeps Zod top-level fields aligned with generated Pydantic schemas', () => {
    expect(Object.keys(ProviderConnectionSchema.shape).sort()).toEqual(
      Object.keys(providerConnectionJsonSchema.properties).sort(),
    )
    expect(Object.keys(AiModelSchema.shape).sort()).toEqual(
      Object.keys(aiModelJsonSchema.properties).sort(),
    )
    expect(Object.keys(AiRouteSchema.shape).sort()).toEqual(
      Object.keys(aiRouteJsonSchema.properties).sort(),
    )
  })

  it('matches shared valid and invalid boundary fixtures', () => {
    const contracts = {
      provider_connection: ProviderConnectionSchema,
      ai_model: AiModelSchema,
      ai_route: AiRouteSchema,
    }

    for (const [name, schema] of Object.entries(contracts)) {
      const fixtures = sharedFixtures[name as keyof typeof sharedFixtures]
      for (const fixture of fixtures.valid) expect(schema.safeParse(fixture).success).toBe(true)
      for (const fixture of fixtures.invalid) expect(schema.safeParse(fixture).success).toBe(false)
    }
  })

  it('aligns required, enum, nullability, numeric and option constraints with JSON Schema', () => {
    expect(providerConnectionJsonSchema.required).toEqual([
      'id',
      'provider_kind',
      'display_name',
      'transport',
      'auth_mode',
    ])
    expect(providerConnectionJsonSchema.properties.provider_kind.enum).toEqual([
      'ollama',
      'openai',
      'google',
      'anthropic',
      'custom',
      'ollama_cloud',
      'openai_compatible',
      'github_copilot',
      'cloud',
      'unknown',
    ])
    expect(providerConnectionJsonSchema.properties.base_url.anyOf).toContainEqual({ type: 'null' })
    expect(aiModelJsonSchema.properties.context_window.anyOf).toContainEqual({ type: 'null' })
    expect(aiModelJsonSchema.properties.context_window.anyOf).toContainEqual({
      exclusiveMinimum: 0,
      type: 'integer',
    })
    const optionsRef = aiRouteJsonSchema.properties.provider_options.$ref
    const optionsName = optionsRef.split('/').at(-1) as keyof typeof aiRouteJsonSchema.$defs
    const optionsSchema = aiRouteJsonSchema.$defs[optionsName]
    expect(optionsSchema.additionalProperties).toBe(false)
    expect(Object.keys(optionsSchema.properties).sort()).toEqual([
      '__legacy_stage_route__',
      'base_url',
      'num_ctx',
    ])
    expect(
      aiRouteJsonSchema.$defs.LegacyStageRouteOptions.properties.reasoning_effort.anyOf,
    ).toContainEqual({ type: 'null' })
  })

  it('mirrors strict backend contracts and keeps unknown capabilities unsupported', () => {
    const capabilities = ModelCapabilitiesSchema.parse({})
    expect(capabilities.chat).toBe('unknown')
    expect(capabilities.vision).toBe('unknown')

    expect(ProviderConnectionSchema.safeParse({ unexpected: true }).success).toBe(false)
    expect(AiModelSchema.safeParse({ unexpected: true }).success).toBe(false)
    expect(AiRouteSchema.safeParse({ unexpected: true }).success).toBe(false)
  })

  it('accepts the canonical Pydantic-shaped payload without secret values', () => {
    const result = ProviderConnectionSchema.safeParse({
      id: 'ollama-local',
      provider_kind: 'ollama',
      display_name: 'Ollama lokal',
      transport: 'local',
      auth_mode: 'none',
      base_url: 'http://localhost:11434',
      enabled: true,
      status: 'connected',
      status_message: null,
      secret_ref: null,
      capabilities: { model_discovery: 'supported' },
      created_at: '2026-07-10T00:00:00Z',
      updated_at: '2026-07-10T00:00:00Z',
      last_tested_at: null,
    })

    expect(result.success).toBe(true)
    expect(ProviderConnectionSchema.safeParse({ ...result.data, api_key: 'forbidden' }).success).toBe(false)
  })

  it.each([
    { 'x-api-key': 'fixture-token' },
    { client_secret: 'fixture-token' },
    { refresh_token: 'fixture-token' },
    { headers: { bearer_token: 'fixture-token' } },
  ])('rejects non-allowlisted provider options: %o', (provider_options) => {
    expect(AiRouteSchema.safeParse({ source: 'runtime', provider_options }).success).toBe(false)
  })

  it('accepts only provider options used by routing', () => {
    expect(AiRouteSchema.safeParse({
      source: 'runtime',
      provider_options: {
        base_url: 'https://gateway.example/v1',
        num_ctx: 32768,
      },
    }).success).toBe(true)
  })

  it.each(sharedFixtures.base_urls.invalid)(
    'rejects non-public base URL in connection and route: %s',
    (base_url) => {
      expect(ProviderConnectionSchema.safeParse(connectionWithBaseUrl(base_url)).success).toBe(false)
      expect(AiRouteSchema.safeParse({
        source: 'runtime',
        provider_options: { base_url },
      }).success).toBe(false)
    },
  )

  it.each(sharedFixtures.base_urls.valid)(
    'accepts public base URL in connection and route: %s',
    (base_url) => {
      expect(ProviderConnectionSchema.safeParse(connectionWithBaseUrl(base_url)).success).toBe(true)
      expect(AiRouteSchema.safeParse({
        source: 'runtime',
        provider_options: { base_url },
      }).success).toBe(true)
    },
  )
})
