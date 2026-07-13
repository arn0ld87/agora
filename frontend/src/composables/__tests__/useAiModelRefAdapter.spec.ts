/**
 * useAiModelRefAdapter — Spec-Tests fuer Slice 5.4 Adapter.
 *
 * Coverage:
 *  1. toStageLlmRoute mit Connection-Lookup (Happy Path)
 *  2. toStageLlmRoute ohne Lookup (defensiver Fallback + console.warn)
 *  3. toAiModelRef mit Provider-Kind-Lookup (Happy Path)
 *  4. toAiModelRef ohne Lookup (defensiver Fallback)
 *  5. toStoredModelString mit und ohne Ref
 *  6. migrateStoredRoute liest neuen Key (AiModelRef-JSON)
 *  7. migrateStoredRoute fällt auf Legacy StageLLMRoute zurück
 *  8. migrateStoredRoute gibt null bei beidem null/korrupt
 *  9. buildProviderKindLookup gruppiert nach provider_kind
 * 10. firstConnectionId liefert erste Connection-ID pro Kind
 * 11. Zod-Spiegel akzeptiert gueltiges AiModelRef
 * 12. Zod-Spiegel lehnt AiModelRef ohne provider_connection_id ab
 * 13. Zod-Spiegel lehnt unbekannte source ab
 * 14. Zod-Spiegel akzeptiert alle AiModelSource-Werte
 * 15. Round-Trip: toStageLlmRoute(toAiModelRef(r)) ist verlustfrei
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  AiModelRefSchema,
  AiModelSourceSchema,
  AiModelRefInputSchema,
  type AiModelRef,
} from '@/contracts/aiModelRef'
import type { StageLLMRoute } from '@/contracts/llmRoutingContract'
import type { ProviderConnection } from '@/contracts/aiProviderContract'
import {
  toStageLlmRoutePure,
  toAiModelRefPure,
  buildProviderKindLookup,
  firstConnectionId,
  toStoredModelStringPure,
  migrateStoredRoutePure,
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

  it('toStageLlmRoute: nimmt provider_kind aus Connection-Lookup (Happy Path)', () => {
    const lookup: ConnectionLookup = new Map([
      ['conn-ollama-1', makeConnection({ id: 'conn-ollama-1', provider_kind: 'ollama' })],
    ])
    const ref: AiModelRef = {
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
      source: 'workspace-default',
    }
    const route = toStageLlmRoutePure(ref, lookup)
    expect(route.provider_id).toBe('ollama')
    expect(route.model).toBe('qwen3')
    expect(route.stage).toBeNull()
    expect(route.reasoning_effort).toBe('none')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('toStageLlmRoute: ohne Lookup faellt auf provider_connection_id zurück und warnt', () => {
    const ref: AiModelRef = {
      provider_connection_id: 'conn-unknown',
      model_id: 'm',
      source: 'explicit',
    }
    const route = toStageLlmRoutePure(ref)
    expect(route.provider_id).toBe('conn-unknown')
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('no connection found for "conn-unknown"'),
    )
  })

  it('toAiModelRef: nimmt connection_id aus Provider-Kind-Lookup (Happy Path)', () => {
    const kindToConn = new Map([['ollama', 'conn-ollama-1']])
    const route: StageLLMRoute = {
      stage: null,
      provider_id: 'ollama',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(route, kindToConn)
    expect(ref.provider_connection_id).toBe('conn-ollama-1')
    expect(ref.model_id).toBe('qwen3')
    expect(ref.source).toBe('explicit')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('toAiModelRef: ohne Lookup faellt auf provider_id zurück und warnt', () => {
    const route: StageLLMRoute = {
      stage: null,
      provider_id: 'openai',
      model: 'gpt-4o-mini',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(route)
    expect(ref.provider_connection_id).toBe('openai')
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('no connection found for provider "openai"'),
    )
  })

  it('toStoredModelString: null → "default", sonst model_id', () => {
    expect(toStoredModelStringPure(null)).toBe('default')
    expect(
      toStoredModelStringPure({
        provider_connection_id: 'c',
        model_id: 'qwen3',
        source: 'explicit',
      }),
    ).toBe('qwen3')
  })

  it('migrateStoredRoute: liest neuen Key (AiModelRef-JSON)', () => {
    const ref: AiModelRef = {
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
      source: 'workspace-default',
    }
    const result = migrateStoredRoutePure(JSON.stringify(ref), null)
    expect(result).toEqual(ref)
  })

  it('migrateStoredRoute: faellt auf Legacy StageLLMRoute zurück (mit Lookup)', () => {
    const route: StageLLMRoute = {
      stage: null,
      provider_id: 'ollama',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const kindToConn = new Map([['ollama', 'conn-ollama-1']])
    const result = migrateStoredRoutePure(null, JSON.stringify(route), kindToConn)
    expect(result).toEqual({
      provider_connection_id: 'conn-ollama-1',
      model_id: 'qwen3',
      source: 'explicit',
    })
  })

  it('migrateStoredRoute: gibt null zurück wenn beides null oder korrupt', () => {
    expect(migrateStoredRoutePure(null, null)).toBeNull()
    expect(migrateStoredRoutePure('kein-json', 'auch-kein-json')).toBeNull()
    expect(migrateStoredRoutePure('{}', '{"model":""}')).toBeNull()
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

  it('Round-Trip: toStageLlmRoute(toAiModelRef(r)) verliert model + provider_id', () => {
    const kindToConn = new Map([['ollama', 'conn-ollama-1']])
    const connLookup: ConnectionLookup = new Map([
      ['conn-ollama-1', makeConnection({ id: 'conn-ollama-1', provider_kind: 'ollama' })],
    ])
    const original: StageLLMRoute = {
      stage: null,
      provider_id: 'ollama',
      model: 'qwen3',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    }
    const ref = toAiModelRefPure(original, kindToConn)
    const back = toStageLlmRoutePure(ref, connLookup)
    expect(back.provider_id).toBe('ollama')
    expect(back.model).toBe('qwen3')
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
