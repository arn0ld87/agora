/**
 * useAiModelRefAdapter — Spec-Tests fuer Slice 5.4 Adapter.
 *
 * Coverage:
 *  1. toLlmRoute mit Connection-Lookup (Happy Path)
 *  2. toLlmRoute ohne Lookup (defensiver Fallback + console.warn)
 *  3. toAiModelRef mit Provider-Kind-Lookup (Happy Path)
 *  4. toAiModelRef ohne Lookup (defensiver Fallback)
 *  5. buildProviderKindLookup gruppiert nach provider_kind
 *  6. firstConnectionId liefert erste Connection-ID pro Kind
 *  7. Zod-Spiegel akzeptiert gueltiges AiModelRef
 *  8. Zod-Spiegel lehnt AiModelRef ohne provider_connection_id ab
 *  9. Zod-Spiegel lehnt unbekannte source ab
 * 10. Zod-Spiegel akzeptiert alle AiModelSource-Werte
 * 11. Round-Trip: toLlmRoute(toAiModelRef(r)) ist verlustfrei
 *
 * Slice 7.6c: Der Legacy-Storage-Migrations-Helper (`migrateStoredRoute*`)
 * wurde mit dem Storage-Cut entfernt; die zugehörigen Tests entfallen.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  AiModelRefSchema,
  AiModelSourceSchema,
  AiModelRefInputSchema,
  type AiModelRef,
} from '@/contracts/aiModelRef'
import type { LlmRoute } from '@/contracts/llmRoute'
import type { ProviderConnection } from '@/contracts/aiProviderContract'
import {
  toLlmRoutePure,
  toAiModelRefPure,
  buildProviderKindLookup,
  firstConnectionId,
  type ConnectionLookup,
} from '../useAiModelRefAdapter'

function makeConnection(overrides: Partial<ProviderConnection> = {}): ProviderConnection {
  return {
    id: 'conn-ollama-1',
    provider_kind: 'ollama',
    display_name: 'Lokales Ollama',
    transport: 'local',
    auth_mode: 'none',
    base_url: 'http://localhost:11434',
    enabled: true,
    status: 'connected',
    status_message: null,
    secret_ref: null,
    capabilities: { chat: 'supported' },
    created_at: null,
    updated_at: null,
    last_tested_at: null,
    ...overrides,
  }
}

describe('useAiModelRefAdapter (Slice 5.4)', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    warnSpy.mockRestore()
  })

  it('toLlmRoute: übernimmt die Connection-ID verlustfrei (Teil 9)', () => {
    const lookup: ConnectionLookup = new Map([
      ['conn-ollama-1', makeConnection({ id: 'conn-ollama-1', provider_kind: 'ollama' })],
    ])
    const ref: AiModelRef = {
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
      source: 'workspace-default',
    }
    const route = toLlmRoutePure(ref, lookup)
    // Teil 9: KEIN Kollaps mehr auf provider_kind ('ollama') — die konkrete
    // Connection-ID bleibt erhalten.
    expect(route.provider_id).toBe('conn-ollama-1')
    expect(route.model).toBe('qwen3')
    expect(route.stage).toBeNull()
    expect(route.reasoning_effort).toBe('none')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('toLlmRoute: übernimmt provider_connection_id auch ohne Lookup', () => {
    const ref: AiModelRef = {
      provider_connection_id: 'conn-unknown',
      model_id: 'm',
      source: 'explicit',
    }
    const route = toLlmRoutePure(ref)
    expect(route.provider_id).toBe('conn-unknown')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('toAiModelRef: mappt Legacy-provider_kind via Lookup auf connection_id', () => {
    const kindToConn = new Map([['ollama', 'conn-ollama-1']])
    const route: LlmRoute = {
      stage: null,
      provider_id: 'ollama',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(route, kindToConn)
    expect(ref).not.toBeNull()
    expect(ref?.provider_connection_id).toBe('conn-ollama-1')
    expect(ref?.model_id).toBe('qwen3')
    expect(ref?.source).toBe('explicit')
  })

  it('toAiModelRef: übernimmt provider_id als connection_id ohne Lookup', () => {
    const route: LlmRoute = {
      stage: null,
      provider_id: 'openai',
      model: 'gpt-4o-mini',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(route)
    expect(ref?.provider_connection_id).toBe('openai')
  })

  it('Teil 10: toAiModelRefPure gibt null bei fehlender provider_id', () => {
    const route: LlmRoute = {
      stage: null,
      provider_id: null,
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    expect(toAiModelRefPure(route)).toBeNull()
  })

  it('Teil 10: toAiModelRefPure gibt null bei fehlendem Modell', () => {
    const route: LlmRoute = {
      stage: null,
      provider_id: 'conn-a',
      model: null,
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    expect(toAiModelRefPure(route)).toBeNull()
  })

  it('Teil 10: toAiModelRefPure-Ergebnis besteht den Zod-Spiegel', () => {
    const route: LlmRoute = {
      stage: null,
      provider_id: 'conn-a',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(route)
    expect(ref).not.toBeNull()
    expect(AiModelRefSchema.safeParse(ref).success).toBe(true)
  })

  it('Teil 9: zwei openai_compatible-Connections bleiben im Roundtrip unterscheidbar', () => {
    const connLookup: ConnectionLookup = new Map([
      ['conn-a', makeConnection({ id: 'conn-a', provider_kind: 'openai_compatible', base_url: 'https://a.example/v1', transport: 'http' })],
      ['conn-b', makeConnection({ id: 'conn-b', provider_kind: 'openai_compatible', base_url: 'https://b.example/v1', transport: 'http' })],
    ])
    const refA: AiModelRef = { provider_connection_id: 'conn-a', model_id: 'qwen3', source: 'explicit' }
    const refB: AiModelRef = { provider_connection_id: 'conn-b', model_id: 'qwen3', source: 'explicit' }
    const roundA = toAiModelRefPure(toLlmRoutePure(refA, connLookup))
    const roundB = toAiModelRefPure(toLlmRoutePure(refB, connLookup))
    // Beide Connections teilen provider_kind, bleiben aber via ID unterscheidbar
    // — kein "erste passende Connection"-Fallback.
    expect(roundA?.provider_connection_id).toBe('conn-a')
    expect(roundB?.provider_connection_id).toBe('conn-b')
    expect(roundA?.provider_connection_id).not.toBe(roundB?.provider_connection_id)
  })

  it('buildProviderKindLookup: gruppiert Connections nach provider_kind', () => {
    const lookup = new Map<string, ProviderConnection>([
      ['conn-1', makeConnection({ id: 'conn-1', provider_kind: 'ollama' })],
      ['conn-2', makeConnection({ id: 'conn-2', provider_kind: 'ollama' })],
      ['conn-3', makeConnection({ id: 'conn-3', provider_kind: 'openai' })],
    ])
    const grouped = buildProviderKindLookup(lookup)
    expect(grouped.get('ollama')?.map((c) => c.id)).toEqual(['conn-1', 'conn-2'])
    expect(grouped.get('openai')?.map((c) => c.id)).toEqual(['conn-3'])
    expect(grouped.get('anthropic')).toBeUndefined()
  })

  it('firstConnectionId: liefert erste Connection-ID pro Kind, undefined für unbekannt', () => {
    const lookup = new Map<string, ProviderConnection>([
      ['conn-1', makeConnection({ id: 'conn-1', provider_kind: 'ollama' })],
      ['conn-2', makeConnection({ id: 'conn-2', provider_kind: 'ollama' })],
    ])
    const grouped = buildProviderKindLookup(lookup)
    expect(firstConnectionId(grouped, 'ollama')).toBe('conn-1')
    expect(firstConnectionId(grouped, 'anthropic')).toBeUndefined()
    expect(firstConnectionId(undefined, 'ollama')).toBeUndefined()
  })

  it('Zod-Spiegel: AiModelRef akzeptiert gueltige Eingabe', () => {
    const result = AiModelRefSchema.safeParse({
      provider_connection_id: 'conn-1',
      model_id: 'qwen3',
      source: 'workspace-default',
      capability_filter: 'chat',
      fallback_reason: 'provider_offline',
    })
    expect(result.success).toBe(true)
  })

  it('Zod-Spiegel: AiModelRef lehnt fehlende provider_connection_id ab', () => {
    const result = AiModelRefSchema.safeParse({
      model_id: 'qwen3',
      source: 'explicit',
    })
    expect(result.success).toBe(false)
  })

  it('Zod-Spiegel: AiModelRef lehnt unbekannte source ab', () => {
    const result = AiModelRefSchema.safeParse({
      provider_connection_id: 'c',
      model_id: 'm',
      source: 'made-up-source',
    })
    expect(result.success).toBe(false)
  })

  it('Zod-Spiegel: AiModelSource deckt alle 6 Quellen ab', () => {
    const sources = [
      'stage-override',
      'run-override',
      'project-default',
      'workspace-default',
      'explicit',
      'fallback',
    ]
    for (const source of sources) {
      expect(AiModelSourceSchema.safeParse(source).success).toBe(true)
    }
    expect(AiModelSourceSchema.safeParse('magic').success).toBe(false)
  })

  it('Round-Trip: Legacy-kind wird via Lookup zur connection_id und bleibt danach stabil', () => {
    const kindToConn = new Map([['ollama', 'conn-ollama-1']])
    const connLookup: ConnectionLookup = new Map([
      ['conn-ollama-1', makeConnection({ id: 'conn-ollama-1', provider_kind: 'ollama' })],
    ])
    const original: LlmRoute = {
      stage: null,
      provider_id: 'ollama',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(original, kindToConn)
    expect(ref).not.toBeNull()
    const back = toLlmRoutePure(ref as AiModelRef, connLookup)
    // Teil 9: provider_id trägt jetzt die konkrete Connection-ID.
    expect(back.provider_id).toBe('conn-ollama-1')
    expect(back.model).toBe('qwen3')
    // Zweiter Roundtrip ist idempotent.
    const refAgain = toAiModelRefPure(back)
    expect(refAgain?.provider_connection_id).toBe('conn-ollama-1')
  })

  it('AiModelRefInput-Spiegel: akzeptiert vollständigen Mock-Datensatz', () => {
    const result = AiModelRefInputSchema.safeParse({
      provider_connection_id: 'conn-1',
      provider_kind: 'ollama',
      display_name: 'Lokales Ollama',
      model_id: 'qwen3',
      context_window: 32768,
      capabilities: ['chat', 'streaming'],
      status: 'available',
      is_workspace_default: true,
      local_or_cloud: 'local',
    })
    expect(result.success).toBe(true)
  })
})
