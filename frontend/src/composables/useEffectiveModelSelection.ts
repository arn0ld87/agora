/**
 * useEffectiveModelSelection — die EINZIGE Quelle/Senke für die effektive
 * globale Chat-Modellwahl (Phase-1 Root-Cause-Fix, frontend-next).
 *
 * Vor dieser Konsolidierung schrieben mehrere Flächen in unabhängige, server-
 * seitig NICHT synchrone Senken (`active-config`, `routing/defaults.global`,
 * drei `agora.*.aiModelRef`-localStorage-Keys, Legacy-Profile). Zwei Runtime-
 * Pfade lasen verschiedene Quellen: `llm/client.py` (use_active_config) →
 * `active-config`, `stage_model_router.py` → `routing/defaults.global_default`.
 * Das war die Ursache der gemeldeten „inkonsistenten Modellauswahl“.
 *
 * Kanon (AGENTS.md): `routing/defaults.global_default`, repräsentiert als
 * {@link AiModelRef} über {@link useAiModelRefAdapter}. `active-config` wird
 * beim Schreiben im Gleichschritt mitgezogen, damit beide Runtime-Leser
 * konsistente Werte sehen. Das Backend bleibt unangetastet (reiner FE-Sync);
 * die theoretisch reinere SSoT (active-config delegiert server-seitig an den
 * Workspace-Routing-Store) ist ein bewusst separates Folge-Slice.
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useLlmProvidersStore, useLlmRoutingDefaultsStore } from '@/store/aiModels'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import { setActiveLlmConfig } from '@/api/llmRouting'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type { LlmRoute } from '@/contracts/llmRoute'

export interface EffectiveModelSelection {
  /** Effektive globale Auswahl als AiModelRef (aus global_default via Adapter). */
  effectiveRef: ComputedRef<AiModelRef | null>
  /** Effektive globale Auswahl als LlmRoute (global_default direkt). */
  effectiveRoute: ComputedRef<LlmRoute>
  loading: Ref<boolean>
  error: Ref<string | null>
  /** Lädt Routing-Defaults + Provider-Connections idempotent. */
  ensureLoaded: () => Promise<void>
  /**
   * Kanonischer Schreibpfad: setzt den globalen Default. Aktualisiert
   * `routing/defaults.global` UND `active-config` im Gleichschritt.
   */
  setGlobalSelection: (ref: AiModelRef) => Promise<void>
}

/**
 * Provides the effective global model selection and synchronizes updates across model configuration stores.
 *
 * @returns The effective model reference and route, loading and error state, and actions for loading and updating the global selection
 */
export function useEffectiveModelSelection(): EffectiveModelSelection {
  const defaultsStore = useLlmRoutingDefaultsStore()
  const providersStore = useLlmProvidersStore()
  const adapter = useAiModelRefAdapter()

  const loading = ref(false)
  const error = ref<string | null>(null)

  const effectiveRoute = computed<LlmRoute>(() => defaultsStore.globalDefault)
  const effectiveRef = computed<AiModelRef | null>(() =>
    adapter.toAiModelRef(defaultsStore.globalDefault),
  )

  async function ensureLoaded(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      await Promise.all([
        defaultsStore.hasLoadedOnce ? Promise.resolve() : defaultsStore.load(),
        providersStore.loadConnections(),
      ])
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      throw cause
    } finally {
      loading.value = false
    }
  }

  async function setGlobalSelection(selection: AiModelRef): Promise<void> {
    error.value = null
    const route = adapter.toLlmRoute(selection)
    try {
      // Kanon zuerst: routing/defaults.global_default.
      await defaultsStore.setGlobalDefault(route)
      // Gleichschritt: active-config, damit der generische LLM-Client
      // (client.py use_active_config) denselben Wert liest.
      await setActiveLlmConfig({
        provider_id: selection.provider_connection_id,
        model: selection.model_id,
      })
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      throw cause
    }
  }

  return {
    effectiveRef,
    effectiveRoute,
    loading,
    error,
    ensureLoaded,
    setGlobalSelection,
  }
}
