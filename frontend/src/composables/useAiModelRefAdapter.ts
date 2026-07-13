/**
 * useAiModelRefAdapter — Brücke zwischen AiModelRef (v4) und StageLLMRoute (v3).
 *
 * Slice 5.4: Solange 5.5 die alten v3-Stores und Contracts noch nicht
 * abgeschafft hat, müssen wir die zwei Vertrags-Welten verbinden:
 *
 * - AiModelRef.provider_connection_id (Connection-ID, z. B. "conn-uuid-xyz")
 * - StageLLMRoute.provider_id       (Provider-Typ, z. B. "ollama")
 *
 * Der Adapter nimmt optional einen Connection-Lookup (`Map<connection_id,
 * ProviderConnection>`), um die IDs aufzulösen. Ohne Lookup wird ein
 * defensiver Fallback verwendet (Connection-ID == Provider-ID), der
 * laut macht, wenn er greift (console.warn) — damit Migrationen nicht
 * stillschweigend kaputt gehen.
 *
 * Tests: Die pure-Helper (`toStageLlmRoute`, `toAiModelRef`,
 * `toStoredModelString`, `migrateStoredRoute`) sind ohne Store testbar.
 *
 * Master-Prompt §6.1 (eine Komponente, eine Semantik) + §6.3 (Audit-Trail).
 */
import { useLlmProvidersStore } from '@/store/aiModels'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type { StageLLMRoute } from '@/contracts/llmRoutingContract'
import type { ProviderConnection } from '@/contracts/aiProviderContract'

/** Lookup-Tabelle Connection-ID → ProviderConnection. */
export type ConnectionLookup = ReadonlyMap<string, ProviderConnection>

/** Inverse Lookup: Provider-Typ → Liste möglicher Connection-IDs. */
export type ProviderKindLookup = ReadonlyMap<string, readonly ProviderConnection[]>

export interface AiModelRefAdapter {
  /** Konvertiert AiModelRef → StageLLMRoute (v3-Store, v3-Backend-Endpoint). */
  toStageLlmRoute: (ref: AiModelRef) => StageLLMRoute
  /** Konvertiert StageLLMRoute → AiModelRef (Picker-Anzeige). */
  toAiModelRef: (route: StageLLMRoute) => AiModelRef
  /** STORAGE_MODEL-Spiegel: nur model_id (MainView liest das klassisch). */
  toStoredModelString: (ref: AiModelRef | null) => string
  /** Liest + migriert HeroNewRun-localStorage. Bevorzugt neuen Key,
   *  faellt auf Legacy StageLLMRoute zurueck (Adapter-Konvertierung). */
  migrateStoredRoute: (rawAiRef: string | null, rawLegacyRoute?: string | null) => AiModelRef | null
  /** Lookup-Builder für externe Aufrufer (z. B. Tests). */
  buildLookup: () => ConnectionLookup
}

/**
 * Pure Konvertierung AiModelRef → StageLLMRoute ohne Store-Zugriff.
 * Connection-Lookup ist optional; ohne Lookup wird provider_connection_id
 * als provider_id übernommen und gewarnt.
 */
export function toStageLlmRoutePure(
  ref: AiModelRef,
  lookup?: ConnectionLookup,
): StageLLMRoute {
  const conn = lookup?.get(ref.provider_connection_id)
  const providerId = conn?.provider_kind ?? ref.provider_connection_id
  if (!conn && typeof console !== 'undefined') {
    console.warn(
      `[aiModelRefAdapter] toStageLlmRoute: no connection found for "${ref.provider_connection_id}", using it as provider_id fallback`,
    )
  }
  return {
    stage: null,
    provider_id: providerId,
    model: ref.model_id,
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  }
}

/**
 * Pure Konvertierung StageLLMRoute → AiModelRef.
 * Connection-Lookup nimmt eine provider_kind → connection_id Map.
 * Ohne Lookup: provider_id wird als provider_connection_id übernommen.
 */
export function toAiModelRefPure(
  route: StageLLMRoute,
  providerKindToConnectionId?: ReadonlyMap<string, string>,
): AiModelRef {
  const providerId = route.provider_id ?? ''
  const connectionId = providerKindToConnectionId?.get(providerId) ?? providerId
  if (!providerKindToConnectionId?.has(providerId) && providerId && typeof console !== 'undefined') {
    console.warn(
      `[aiModelRefAdapter] toAiModelRef: no connection found for provider "${providerId}", using provider_id as connection_id fallback`,
    )
  }
  return {
    provider_connection_id: connectionId,
    model_id: route.model ?? '',
    source: 'explicit',
  }
}

/** Map-Builder: provider_kind → erste passende Connection-ID. */
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

/** Erste Connection-ID für einen Provider-Typ oder undefined. */
export function firstConnectionId(
  lookup: ProviderKindLookup | undefined,
  providerKind: string,
): string | undefined {
  return lookup?.get(providerKind)?.[0]?.id
}

/** STORAGE_MODEL-Spiegel — nur model_id. */
export function toStoredModelStringPure(ref: AiModelRef | null): string {
  return ref?.model_id ?? 'default'
}

/**
 * Liest HeroNewRun-localStorage und gibt ein AiModelRef | null zurück.
 * Versucht zuerst den neuen Key `agora.hero.aiModelRef` (AiModelRef-JSON),
 * fällt dann zurück auf `agora.hero.route` (StageLLMRoute-JSON, alt)
 * und konvertiert via `toAiModelRefPure` mit dem mitgegebenen Lookup.
 * Kein Storage-Schreiben — das macht der Aufrufer (HeroNewRun) explizit.
 */
export function migrateStoredRoutePure(
  rawAiRef: string | null,
  rawLegacyRoute: string | null,
  providerKindToConnectionId?: ReadonlyMap<string, string>,
): AiModelRef | null {
  if (rawAiRef) {
    try {
      const parsed = JSON.parse(rawAiRef) as unknown
      if (
        parsed && typeof parsed === 'object'
        && 'provider_connection_id' in parsed
        && 'model_id' in parsed
        && typeof (parsed as { provider_connection_id: unknown }).provider_connection_id === 'string'
        && typeof (parsed as { model_id: unknown }).model_id === 'string'
      ) {
        return parsed as AiModelRef
      }
    } catch {
      /* fall through to legacy */
    }
  }
  if (rawLegacyRoute) {
    try {
      const parsed = JSON.parse(rawLegacyRoute) as StageLLMRoute
      if (parsed?.model) {
        return toAiModelRefPure(parsed, providerKindToConnectionId)
      }
    } catch {
      /* noop */
    }
  }
  return null
}

/** Composable-Factory, die den LlmProvidersStore nutzt (Vue-Composition-API). */
export function useAiModelRefAdapter(): AiModelRefAdapter {
  const store = useLlmProvidersStore()
  const buildLookup = (): ConnectionLookup => {
    const map = new Map<string, ProviderConnection>()
    for (const conn of Object.values(store.connections)) {
      map.set(conn.id, conn)
    }
    return map
  }
  const toStageLlmRoute = (ref: AiModelRef): StageLLMRoute =>
    toStageLlmRoutePure(ref, buildLookup())
  const toAiModelRef = (route: StageLLMRoute): AiModelRef => {
    const kindLookup = buildProviderKindLookup(buildLookup())
    return toAiModelRefPure(route, firstConnectionIdByKind(kindLookup))
  }
  const toStoredModelString = (ref: AiModelRef | null): string =>
    toStoredModelStringPure(ref)
  const migrateStoredRoute = (rawAiRef: string | null, rawLegacyRoute: string | null = null): AiModelRef | null => {
    const kindLookup = buildProviderKindLookup(buildLookup())
    return migrateStoredRoutePure(
      rawAiRef,
      rawLegacyRoute,
      firstConnectionIdByKind(kindLookup),
    )
  }
  return { toStageLlmRoute, toAiModelRef, toStoredModelString, migrateStoredRoute, buildLookup }
}

/** Convenience: provider_kind → erste connection_id Map. */
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
