import { describe, expect, it } from 'vitest'

import aiModelJsonSchema from '../../../../schemas/ai-model.schema.json'
import aiRouteJsonSchema from '../../../../schemas/ai-route.schema.json'
import providerConnectionJsonSchema from '../../../../schemas/ai-provider-connection.schema.json'
import sharedFixtures from '../../../../schemas/fixtures/ai-provider-contract-fixtures.json'

import {
  AiModelSchema,
  AiProviderOptionsSchema,
  AiRouteSchema,
  ModelCapabilitiesSchema,
  ProviderConnectionBaseSchema,
  ProviderConnectionSchema,
  ProviderConnectionResponseSchema,
  ProviderConnectionUpsertRequestSchema,
  LegacyStageRouteOptionsSchema,
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
    expect(Object.keys(ProviderConnectionBaseSchema.shape).sort()).toEqual(
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
      'minimax',
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
    expect(Object.keys(AiProviderOptionsSchema.shape).sort()).toEqual(
      Object.keys(optionsSchema.properties).sort(),
    )
    expect(Object.keys(optionsSchema.properties).sort()).toEqual([
      '__legacy_stage_route__',
      'base_url',
      'connection_only',
      'num_ctx',
      'secret_ref',
    ])
    expect(
      aiRouteJsonSchema.$defs.LegacyStageRouteOptions.properties.reasoning_effort.anyOf,
    ).toContainEqual({ type: 'null' })

    // Issue #901: Der Legacy-Kanal war bisher nur punktuell geprüft — die
    // Key-Parität oben galt allein `AiProviderOptionsSchema`. Genau deshalb
    // konnte `ai_model_ref_source` im Backend landen, ohne dass der `.strict()`
    // -Spiegel es bemerkte. Dieselbe Paritätsaussage gilt jetzt auch hier.
    const legacySchema = aiRouteJsonSchema.$defs.LegacyStageRouteOptions
    expect(legacySchema.additionalProperties).toBe(false)
    expect(Object.keys(LegacyStageRouteOptionsSchema.shape).sort()).toEqual(
      Object.keys(legacySchema.properties).sort(),
    )
  })

  it('accepts and rejects ai_model_ref_source in the legacy channel per contract', () => {
    const base = {
      temperature: null,
      max_tokens: null,
      reasoning_effort: null,
      had_reserved_value: false,
      reserved_value: null,
    }

    // NotRequired[AiModelRefSource | None] — fehlend, null und gültiger Wert
    // müssen alle durchgehen; Bestands-Options ohne den Schlüssel dürfen nicht
    // brechen.
    expect(LegacyStageRouteOptionsSchema.safeParse(base).success).toBe(true)
    expect(LegacyStageRouteOptionsSchema.safeParse({ ...base, ai_model_ref_source: null }).success).toBe(true)
    expect(
      LegacyStageRouteOptionsSchema.safeParse({ ...base, ai_model_ref_source: 'stage-override' }).success,
    ).toBe(true)

    // Kein RouteSource-Vokabular: die beiden Enums sind bewusst getrennt,
    // ein Unterstrich-Wert wäre eine stille Vermischung.
    expect(
      LegacyStageRouteOptionsSchema.safeParse({ ...base, ai_model_ref_source: 'stage_override' }).success,
    ).toBe(false)
  })

  it('accepts fallback_reason in the legacy channel and stays strict about unknown keys', () => {
    // Issue #992: `fallback_reason` reist im Legacy-Kanal mit, weil
    // `resolve_ai_route` das oberste `AiRoute.fallback_reason` für jeden Slot
    // außer `provider_fallback` löscht. Ohne diesen Spiegel wäre der neue
    // Schlüssel im Backend gelandet, ohne dass `.strict()` es bemerkt — genau
    // der Fall, der in #901 schon einmal durchgerutscht ist.
    const base = {
      temperature: null,
      max_tokens: null,
      reasoning_effort: null,
      had_reserved_value: false,
      reserved_value: null,
    }

    // NotRequired[str | None] — fehlend, null und ein Textwert gehen durch.
    expect(LegacyStageRouteOptionsSchema.safeParse(base).success).toBe(true)
    expect(LegacyStageRouteOptionsSchema.safeParse({ ...base, fallback_reason: null }).success).toBe(true)
    expect(
      LegacyStageRouteOptionsSchema.safeParse({ ...base, fallback_reason: 'Primaermodell nicht erreichbar' })
        .success,
    ).toBe(true)
    // Der leere String ist ein gültiger Wert und darf nicht wie `null`
    // behandelt werden — Backend-seitig wird deshalb auf `is None` geprüft
    // und nicht auf den Wahrheitswert.
    expect(LegacyStageRouteOptionsSchema.safeParse({ ...base, fallback_reason: '' }).success).toBe(true)

    // Falscher Typ bleibt ein Fehler.
    expect(LegacyStageRouteOptionsSchema.safeParse({ ...base, fallback_reason: 42 }).success).toBe(false)

    // `.strict()` gilt weiterhin: ein benachbarter, nicht deklarierter
    // Schlüssel wird abgelehnt. Ohne diese Zusicherung würde der Test oben
    // auch dann grün, wenn das Schema versehentlich durchlässig würde.
    expect(
      LegacyStageRouteOptionsSchema.safeParse({ ...base, fallback_reasons: 'tippfehler' }).success,
    ).toBe(false)
  })

  it('mirrors strict backend contracts and keeps unknown capabilities unsupported', () => {
    const capabilities = ModelCapabilitiesSchema.parse({})
    expect(capabilities.chat).toBe('unknown')
    expect(capabilities.vision).toBe('unknown')

    expect(ProviderConnectionSchema.safeParse({ unexpected: true }).success).toBe(false)
    expect(AiModelSchema.safeParse({ unexpected: true }).success).toBe(false)
    expect(AiRouteSchema.safeParse({ unexpected: true }).success).toBe(false)
  })

  it.each(['run_override', 'project', 'workspace'])(
    'accepts the additive route source %s',
    (source) => {
      expect(AiRouteSchema.safeParse({
        source,
        resolved_at: '2026-07-13T10:30:00Z',
      }).success).toBe(true)
    },
  )

  it('requires a non-blank reason for provider fallback routes', () => {
    expect(AiRouteSchema.safeParse({
      source: 'provider_fallback',
      fallback_reason: 'No configured route was available',
      resolved_at: '2026-07-13T10:30:00Z',
    }).success).toBe(true)
    expect(AiRouteSchema.safeParse({ source: 'provider_fallback' }).success).toBe(false)
    expect(AiRouteSchema.safeParse({
      source: 'provider_fallback',
      fallback_reason: '   ',
    }).success).toBe(false)
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

  it('accepts minimax in lifecycle requests', () => {
    expect(ProviderConnectionUpsertRequestSchema.safeParse({
      display_name: 'Cloud provider',
      provider_kind: 'minimax',
      base_url: 'https://api.example.test/v1',
    }).success).toBe(true)
  })

  it('keeps OpenCode Go unsupported in public provider connection contracts', () => {
    expect(ProviderConnectionUpsertRequestSchema.safeParse({
      display_name: 'OpenCode Go',
      provider_kind: 'opencode_go',
      base_url: 'https://api.example.test/v1',
    }).success).toBe(false)
    expect(ProviderConnectionSchema.safeParse({
      ...connectionWithBaseUrl('https://api.example.test/v1'),
      provider_kind: 'opencode_go',
    }).success).toBe(false)
  })

  // Spiegel von backend/tests/contracts/test_ai_provider_contract.py.
  // `host.docker.internal` ist im Container-Betrieb die einzige Adresse, unter
  // der ein auf dem Host laufendes Ollama erreichbar ist — `localhost` zeigt
  // dort auf den Container selbst.
  it.each([
    'http://127.0.0.1:11434',
    'http://[::1]:11434/v1',
    'http://localhost:11434',
    'http://host.docker.internal:11434',
    'http://HOST.DOCKER.INTERNAL:11434',
  ])(
    'accepts a local Ollama URL: %s',
    (base_url) => {
      expect(ProviderConnectionUpsertRequestSchema.safeParse({
        display_name: 'Ollama lokal',
        provider_kind: 'ollama',
        base_url,
      }).success).toBe(true)
    },
  )

  it.each([
    'https://ollama.example.test',
    'http://192.168.1.10:11434',
    // Bind-, keine Ziel-Adresse.
    'http://0.0.0.0:11434',
    // Kein Subdomain-Smuggling über den Docker-Hostnamen.
    'http://host.docker.internal.attacker.test:11434',
    'http://not-host.docker.internal:11434',
  ])(
    'rejects a non-local URL for local Ollama: %s',
    (base_url) => {
      expect(ProviderConnectionUpsertRequestSchema.safeParse({
        display_name: 'Ollama lokal',
        provider_kind: 'ollama',
        base_url,
      }).success).toBe(false)
    },
  )

  it('rejects a loopback URL for a non-local provider connection', () => {
    expect(ProviderConnectionSchema.safeParse({
      ...connectionWithBaseUrl('http://localhost:11434'),
      provider_kind: 'openai_compatible',
    }).success).toBe(false)
  })

  it('keeps API keys input-only and rejects them from public responses', () => {
    expect(ProviderConnectionUpsertRequestSchema.safeParse({
      display_name: 'OpenAI',
      provider_kind: 'openai',
      api_key: 'test-only-api-key',
    }).success).toBe(true)
    expect(ProviderConnectionResponseSchema.safeParse({
      connection: { ...connectionWithBaseUrl('https://api.openai.com/v1'), api_key: 'test-only-api-key' },
    }).success).toBe(false)
  })

  it.each([
    { timeout: 30 },
    { api_key: 'forbidden-placeholder' },
    { 'x-api-key': 'fixture-token' },
    { client_secret: 'fixture-token' },
    { refresh_token: 'fixture-token' },
    { headers: { bearer_token: 'fixture-token' } },
  ])('rejects non-allowlisted provider options: %o', (provider_options) => {
    expect(AiRouteSchema.safeParse({ source: 'runtime', provider_options }).success).toBe(false)
  })

  it('accepts strict secret-free provider metadata used by routing', () => {
    expect(AiRouteSchema.safeParse({
      source: 'runtime',
      provider_options: {
        base_url: 'https://gateway.example/v1',
        connection_only: true,
        num_ctx: 32768,
        secret_ref: 'provider-secret-reference',
      },
    }).success).toBe(true)
  })

  it('rejects an empty provider secret reference', () => {
    expect(AiRouteSchema.safeParse({
      source: 'runtime',
      provider_options: { secret_ref: '' },
    }).success).toBe(false)
  })

  it('requires a provider secret reference for connection-only routing', () => {
    expect(AiRouteSchema.safeParse({
      source: 'runtime',
      provider_options: { connection_only: true },
    }).success).toBe(false)
  })

  it.each([
    { connection_only: false },
    { secret_ref: 'provider-secret-reference' },
  ])('keeps independent provider metadata valid: %o', (provider_options) => {
    expect(AiRouteSchema.safeParse({ source: 'runtime', provider_options }).success).toBe(true)
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
