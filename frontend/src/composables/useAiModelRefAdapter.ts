/**
 * useAiModelRefAdapter — Brücke zwischen AiModelRef (v4) und LlmRoute (Backend-Body).
 *
 * Slice 5.4: Solange 5.5 die alten v3-Stores und Contracts noch nicht
 * abgeschafft hat, müssen wir die zwei Vertrags-Welten verbinden:
 *
 * - AiModelRef.provider_connection_id (Connection-ID, z. B. "conn-uuid-xyz")
 * - LlmRoute.provider_id            (Provider-Connection-ID, identisch seit 7.3.3)
 *
 * Tests: Die pure-Helper (`toLlmRoutePure`, `toAiModelRefPure`,
 * `toStoredModelStringPure`) sind ohne Store testbar.
 *
 * Slice 7.6c: Body-Type heißt `LlmRoute` (siehe `frontend/src/contracts/llmRoute.ts`).
 * Das Backend bleibt Pydantic-SSoT, der Frontend-Type ist nur die
 * Boundary-Repräsentation an `/api/llm-routing`-Endpoints. Der Legacy-Storage-
 * Migrations-Helper wurde mit dem Storage-Cut entfernt.
 */
import { useLlmProvidersStore } from '@/store/aiModels'
import { AiModelRefSchema, type AiModelRef } from '@/contracts/aiModelRef'
import type { LlmRoute } from '@/contracts/llmRoute'
import type { ProviderConnection } from '@/contracts/aiProviderContract'

export type ConnectionLookup = ReadonlyMap<string, ProviderConnection>
export type ProviderKindLookup = ReadonlyMap<string, readonly ProviderConnection[]>

export interface AiModelRefAdapter {
  /** Konvertiert AiModelRef → LlmRoute (Backend-Body). */
  toLlmRoute: (ref: AiModelRef) => LlmRoute
  /** Konvertiert LlmRoute → AiModelRef (Picker-Anzeige). `null`, wenn
   *  die Route keine gültige Provider-Connection-ID + Modell trägt. */
  toAiModelRef: (route: LlmRoute) => AiModelRef | null
  /** STORAGE_MODEL-Spiegel: nur model_id (MainView liest das klassisch). */
  toStoredModelString: (ref: AiModelRef | null) => string
  /** Lookup-Builder für externe Aufrufer (z. B. Tests). */
  buildLookup: () => ConnectionLookup
}

export function toLlmRoutePure(
  ref: AiModelRef,
  _lookup?: ConnectionLookup,
): LlmRoute {
  return {
    stage: null,
    provider_id: ref.provider_connection_id,
    model: ref.model_id,
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  }
}

export function toAiModelRefPure(
  route: LlmRoute,
  lookup?: ReadonlyMap<string, string>,
): AiModelRef | null {
  if (!route.provider_id || !route.model) return null
  const candidate: AiModelRef = {
    provider_connection_id: lookup?.get(route.provider_id) ?? route.provider_id,
    model_id: route.model,
    source: 'explicit',
  }
  return AiModelRefSchema.safeParse(candidate).success ? candidate : null
}

export function buildProviderKindLookup(
  connections: ReadonlyMap<string, ProviderConnection>,
): ProviderKindLookup {
  const out = new Map<string, ProviderConnection[]>()
  for (const conn of connections.values()) {
    const list = out.get(conn.provider_kind) ?? []
    list.push(conn)
    out.set(conn.provider_kind, list)
  }
  return out
}

export function firstConnectionId(
  lookup: ProviderKindLookup | undefined,
  providerKind: string,
): string | undefined {
  return lookup?.get(providerKind)?.[0]?.id
}

export function toStoredModelStringPure(ref: AiModelRef | null): string {
  return ref?.model_id ?? 'default'
}

export function useAiModelRefAdapter(): AiModelRefAdapter {
  const store = useLlmProvidersStore()
  const buildLookup = (): ConnectionLookup => {
    const map = new Map<string, ProviderConnection>()
    for (const conn of Object.values(store.connections)) {
      map.set(conn.id, conn)
    }
    return map
  }
  const toLlmRoute = (ref: AiModelRef): LlmRoute =>
    toLlmRoutePure(ref, buildLookup())
  const toAiModelRef = (route: LlmRoute): AiModelRef | null => {
    const kindLookup = buildProviderKindLookup(buildLookup())
    return toAiModelRefPure(route, firstConnectionIdByKind(kindLookup))
  }
  const toStoredModelString = (ref: AiModelRef | null): string =>
    toStoredModelStringPure(ref)
  return { toLlmRoute, toAiModelRef, toStoredModelString, buildLookup }
}

function firstConnectionIdByKind(
  kindLookup: ProviderKindLookup,
): ReadonlyMap<string, string> {
  const out = new Map<string, string>()
  for (const [kind, list] of kindLookup) {
    const first = list[0]
    if (first) out.set(kind, first.id)
  }
  return out
}