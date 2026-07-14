/**
 * aiModels — konsolidierter Pinia-Store für die AI-Modell-Domäne.
 *
 * Sub-Slice 5.5 der Epic ``onboarding-provider-unification`` führt die drei
 * zuvor getrennten Stores in dieses Modul zusammen (SSoT für „welches Modell
 * nimmt der Run?", Master-Prompt §5.3 / §6.1):
 *
 *   - ``llmProviders``        → Provider-Descriptors, Legacy-Keys, kanonischer
 *                               Provider-Connection-Lifecycle (Onboarding 3)
 *   - ``llmProfiles``         → LLM-Profil-CRUD (P5.4)
 *   - ``llmRoutingDefaults``  → Workspace-weite Default-Route + Stage-Overrides
 *
 * Die Pinia-Store-IDs (``llmProviders``, ``llmProfiles``, ``llmRoutingDefaults``)
 * bleiben unverändert — bestehende persistierte States und das Test-Verhalten
 * ändern sich nicht. Neu ist nur die **eine** Import-Oberfläche
 * ``@/store/aiModels`` plus die Facade ``useAiModelsStore()``, die alle drei
 * Teil-Stores gebündelt zurückgibt.
 *
 * Der Grep-CI-Check (``check_legacy_model_picker.py``) verbietet die alten
 * Import-Specifier ``@/store/llmProviders`` / ``…/llmProfiles`` /
 * ``…/llmRoutingDefaults`` — sie existieren nach 5.5 nicht mehr als Datei.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";

import { listLlmProviders } from "../api/llmRouting";
import {
  deleteLlmProviderKey,
  listLlmProviderKeys,
  upsertLlmProviderKey,
  testLlmProvider,
  type ProviderTestResult,
} from "../api/llmProviderKeys";
import {
  deleteProviderConnection,
  listProviderConnectionModels,
  listProviderConnections,
  testProviderConnection,
  upsertProviderConnection,
  type ProviderConnectionUpsertPayload,
} from "../api/providerConnections";
import {
  fetchLlmProfiles,
  createLlmProfile,
  updateLlmProfile,
  deleteLlmProfile,
  setDefaultLlmProfile,
} from "../api/llmProfiles";
import {
  getRoutingDefaults,
  patchRoutingDefaultStage,
  replaceGlobalDefault,
  replaceRoutingDefaults,
} from "../api/llmRoutingDefaults";
import service from "../api";
import type { ApiSuccessEnvelope } from "../api/envelope";
import { isApiError } from "../api/envelope";
import { unwrapResponse } from "../api/parse";

import type { ProviderDescriptor, StageId } from "../contracts/llmRoutingContract";
import type { LlmRoute } from "../contracts/llmRoute";
import type { LlmProviderKeyEntry } from "../contracts/llmProviderKeysContract";
import type { LlmProfile, LlmProfileCreateRequest } from "../contracts/llmProfileContract";
import type { WorkspaceLlmRoutingDefaults } from "../contracts/workspaceRoutingContract";
import type {
  AiModel,
  ProviderConnection,
  ProviderConnectionTestResult,
} from "../contracts/aiProviderContract";

// ---------------------------------------------------------------------------
// llmProviders — Provider-Descriptors, Legacy-Keys, Connection-Lifecycle
// ---------------------------------------------------------------------------

interface ModelEntry {
  id: string;
  name: string;
  provider_id: string;
  source: "live" | "cached" | "fallback" | "custom";
  refreshed_at: number;
}

interface ModelCache {
  models: ModelEntry[];
  fetchedAt: number;
}

const MODEL_CACHE_TTL_MS = 10 * 60 * 1000;

export const useLlmProvidersStore = defineStore("llmProviders", () => {
  const providers = ref<ProviderDescriptor[]>([]);
  const entries = ref<Record<string, LlmProviderKeyEntry>>({});
  const models = ref<Record<string, ModelCache>>({});
  const loading = ref(false);
  const busy = ref<Record<string, boolean>>({});
  const lastError = ref<Record<string, string | null>>({});

  async function loadProviders(): Promise<void> {
    loading.value = true;
    try {
      const [list, keys] = await Promise.all([listLlmProviders(), listLlmProviderKeys()]);
      providers.value = list;
      entries.value = Object.fromEntries(keys.items.map((k) => [k.provider_id, k]));
    } catch (err) {
      console.error("Failed to load LLM providers:", err);
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function fetchModels(providerId: string, opts: { force?: boolean } = {}): Promise<ModelEntry[]> {
    const cached = models.value[providerId];
    if (!opts.force && cached && Date.now() - cached.fetchedAt < MODEL_CACHE_TTL_MS) {
      return cached.models;
    }
    busy.value = { ...busy.value, [providerId]: true };
    lastError.value = { ...lastError.value, [providerId]: null };
    try {
      const provider = providers.value.find((p) => p.id === providerId);
      const baseUrl = entries.value[providerId]?.base_url || provider?.base_url || undefined;
      const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
      const resp = await service.get<ApiSuccessEnvelope<ModelEntry[]>>(
        `/api/llm/providers/${providerId}/models${query}`,
      );
      const list = unwrapResponse<ModelEntry[]>(resp);
      models.value = {
        ...models.value,
        [providerId]: { models: list, fetchedAt: Date.now() },
      };
      return list;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      lastError.value = { ...lastError.value, [providerId]: message };
      throw err;
    } finally {
      busy.value = { ...busy.value, [providerId]: false };
    }
  }

  async function saveKey(
    providerId: string,
    apiKey: string,
    baseUrl?: string,
    options: { validate?: boolean } = {},
  ): Promise<LlmProviderKeyEntry> {
    busy.value = { ...busy.value, [providerId]: true };
    lastError.value = { ...lastError.value, [providerId]: null };
    try {
      const entry = await upsertLlmProviderKey(
        providerId,
        { api_key: apiKey, base_url: baseUrl || null },
        options,
      );
      entries.value = { ...entries.value, [providerId]: entry };
      // Modell-Cache invalidieren, weil neuer Key u. U. mehr Modelle freigibt
      delete models.value[providerId];
      return entry;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      lastError.value = { ...lastError.value, [providerId]: message };
      throw err;
    } finally {
      busy.value = { ...busy.value, [providerId]: false };
    }
  }

  async function revokeKey(providerId: string): Promise<void> {
    busy.value = { ...busy.value, [providerId]: true };
    lastError.value = { ...lastError.value, [providerId]: null };
    try {
      await deleteLlmProviderKey(providerId);
      const next = { ...entries.value };
      delete next[providerId];
      entries.value = next;
      delete models.value[providerId];
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      lastError.value = { ...lastError.value, [providerId]: message };
      throw err;
    } finally {
      busy.value = { ...busy.value, [providerId]: false };
    }
  }

  async function testProvider(
    providerId: string,
    payload: { api_key?: string; base_url?: string } = {},
    options: { inference?: boolean } = {},
  ): Promise<ProviderTestResult> {
    busy.value = { ...busy.value, [providerId]: true };
    lastError.value = { ...lastError.value, [providerId]: null };
    try {
      return await testLlmProvider(providerId, payload, options);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      lastError.value = { ...lastError.value, [providerId]: message };
      throw err;
    } finally {
      busy.value = { ...busy.value, [providerId]: false };
    }
  }

  function hasKey(providerId: string): boolean {
    return providerId in entries.value;
  }

  // ---------------------------------------------------------------------
  // Kanonischer Connection-Lifecycle (Onboarding Slice 3, Task 5).
  //
  // Additiv zum Legacy-State oben: `connections` hält ausschließlich
  // secret-freie `ProviderConnection`-Metadaten aus dem Backend-Contract.
  // Ein `api_key` wird hier nie zwischengespeichert — er verlässt diesen
  // Store nur als Argument von `upsertConnection` in Richtung Backend.
  // ---------------------------------------------------------------------

  const connections = ref<Record<string, ProviderConnection>>({});
  const connectionsLoading = ref(false);
  const connectionBusy = ref<Record<string, boolean>>({});
  const connectionError = ref<Record<string, string | null>>({});
  // 409 provider_unsupported (z.B. Subscription-/CLI-Bridges): ehrlich als
  // "nicht unterstützt" markieren statt eine Verbindung vorzutäuschen.
  const connectionUnsupported = ref<Record<string, boolean>>({});
  const connectionTestResults = ref<Record<string, ProviderConnectionTestResult>>({});
  const connectionModels = ref<Record<string, AiModel[]>>({});

  function isConnectionConfigured(connectionId: string): boolean {
    return connectionId in connections.value;
  }

  async function loadConnections(): Promise<void> {
    connectionsLoading.value = true;
    try {
      const { items } = await listProviderConnections();
      connections.value = Object.fromEntries(items.map((c) => [c.id, c]));
    } catch (err) {
      console.error("Failed to load provider connections:", err);
      throw err;
    } finally {
      connectionsLoading.value = false;
    }
  }

  function markUnsupportedIfApplicable(connectionId: string, err: unknown): void {
    if (isApiError(err) && err.code === "provider_unsupported") {
      connectionUnsupported.value = { ...connectionUnsupported.value, [connectionId]: true };
    }
  }

  async function upsertConnection(
    connectionId: string,
    payload: ProviderConnectionUpsertPayload,
  ): Promise<ProviderConnection> {
    connectionBusy.value = { ...connectionBusy.value, [connectionId]: true };
    connectionError.value = { ...connectionError.value, [connectionId]: null };
    try {
      const connection = await upsertProviderConnection(connectionId, payload);
      connections.value = { ...connections.value, [connectionId]: connection };
      delete connectionTestResults.value[connectionId];
      delete connectionModels.value[connectionId];
      return connection;
    } catch (err) {
      markUnsupportedIfApplicable(connectionId, err);
      const message = err instanceof Error ? err.message : String(err);
      connectionError.value = { ...connectionError.value, [connectionId]: message };
      throw err;
    } finally {
      connectionBusy.value = { ...connectionBusy.value, [connectionId]: false };
    }
  }

  async function removeConnection(connectionId: string): Promise<void> {
    connectionBusy.value = { ...connectionBusy.value, [connectionId]: true };
    connectionError.value = { ...connectionError.value, [connectionId]: null };
    try {
      await deleteProviderConnection(connectionId);
      const nextConnections = { ...connections.value };
      delete nextConnections[connectionId];
      connections.value = nextConnections;
      delete connectionTestResults.value[connectionId];
      delete connectionModels.value[connectionId];
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      connectionError.value = { ...connectionError.value, [connectionId]: message };
      throw err;
    } finally {
      connectionBusy.value = { ...connectionBusy.value, [connectionId]: false };
    }
  }

  async function testConnection(connectionId: string): Promise<ProviderConnectionTestResult> {
    connectionBusy.value = { ...connectionBusy.value, [connectionId]: true };
    connectionError.value = { ...connectionError.value, [connectionId]: null };
    try {
      const result = await testProviderConnection(connectionId);
      connectionTestResults.value = { ...connectionTestResults.value, [connectionId]: result };
      // Der Test-Response trägt nur das rohe Probe-Ergebnis; der persistierte
      // Connection-Status wird server-seitig aktualisiert (update_probe) —
      // frisch nachladen statt die Status-Mapping-Tabelle client-seitig zu
      // duplizieren (Provider-Drift-Risiko, siehe Design-Doc).
      await loadConnections();
      return result;
    } catch (err) {
      markUnsupportedIfApplicable(connectionId, err);
      const message = err instanceof Error ? err.message : String(err);
      connectionError.value = { ...connectionError.value, [connectionId]: message };
      throw err;
    } finally {
      connectionBusy.value = { ...connectionBusy.value, [connectionId]: false };
    }
  }

  async function fetchConnectionModels(connectionId: string): Promise<AiModel[]> {
    connectionBusy.value = { ...connectionBusy.value, [connectionId]: true };
    connectionError.value = { ...connectionError.value, [connectionId]: null };
    try {
      const list = await listProviderConnectionModels(connectionId);
      connectionModels.value = { ...connectionModels.value, [connectionId]: list };
      return list;
    } catch (err) {
      markUnsupportedIfApplicable(connectionId, err);
      const message = err instanceof Error ? err.message : String(err);
      connectionError.value = { ...connectionError.value, [connectionId]: message };
      throw err;
    } finally {
      connectionBusy.value = { ...connectionBusy.value, [connectionId]: false };
    }
  }

  return {
    providers,
    entries,
    models,
    loading,
    busy,
    lastError,
    loadProviders,
    fetchModels,
    saveKey,
    revokeKey,
    testProvider,
    hasKey,
    connections,
    connectionsLoading,
    connectionBusy,
    connectionError,
    connectionUnsupported,
    connectionTestResults,
    connectionModels,
    isConnectionConfigured,
    loadConnections,
    upsertConnection,
    removeConnection,
    testConnection,
    fetchConnectionModels,
  };
});

// ---------------------------------------------------------------------------
// llmProfiles — LLM-Profil-CRUD (P5.4)
// ---------------------------------------------------------------------------

export const useLlmProfilesStore = defineStore("llmProfiles", () => {
  const profiles = ref<LlmProfile[]>([]);
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);

  async function fetch(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      profiles.value = await fetchLlmProfiles();
    } catch (err) {
      const e = err as Error;
      error.value = e?.message ?? "Fehler beim Laden der LLM-Profile.";
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function create(req: LlmProfileCreateRequest): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      const created = await createLlmProfile(req);
      profiles.value = [created, ...profiles.value];
    } catch (err) {
      const e = err as Error;
      error.value = e?.message ?? "Fehler beim Anlegen des Profils.";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function update(id: string, req: LlmProfileCreateRequest): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      const updated = await updateLlmProfile(id, req);
      const idx = profiles.value.findIndex((p) => p.id === id);
      if (idx !== -1) {
        profiles.value = [
          ...profiles.value.slice(0, idx),
          updated,
          ...profiles.value.slice(idx + 1),
        ];
      }
    } catch (err) {
      const e = err as Error;
      error.value = e?.message ?? "Fehler beim Aktualisieren des Profils.";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function remove(id: string): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      await deleteLlmProfile(id);
      profiles.value = profiles.value.filter((p) => p.id !== id);
    } catch (err) {
      const e = err as Error;
      error.value = e?.message ?? "Fehler beim Löschen des Profils.";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  async function setDefault(id: string): Promise<void> {
    saving.value = true;
    error.value = null;
    try {
      const updated = await setDefaultLlmProfile(id);
      // Alle is_default lokal zurücksetzen, dann das zurückgegebene ersetzen.
      const reset = profiles.value.map((p) => ({ ...p, is_default: false }));
      const idx = reset.findIndex((p) => p.id === id);
      if (idx !== -1) {
        profiles.value = [
          ...reset.slice(0, idx),
          updated,
          ...reset.slice(idx + 1),
        ];
      } else {
        profiles.value = reset;
      }
    } catch (err) {
      const e = err as Error;
      error.value = e?.message ?? "Fehler beim Setzen des Standard-Profils.";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  return {
    profiles,
    loading,
    saving,
    error,
    fetch,
    create,
    update,
    remove,
    setDefault,
  };
});

// ---------------------------------------------------------------------------
// llmRoutingDefaults — Workspace-weite Default-Route + Stage-Overrides
// ---------------------------------------------------------------------------

const EMPTY_DEFAULTS: WorkspaceLlmRoutingDefaults = {
  global_default: {
    stage: null,
    provider_id: null,
    model: null,
    temperature: null,
    max_tokens: null,
    reasoning_effort: "none",
    provider_options: {},
  },
  stage_overrides: {},
  version: 1,
  updated_at: null,
};

export const useLlmRoutingDefaultsStore = defineStore("llmRoutingDefaults", () => {
  const defaults = ref<WorkspaceLlmRoutingDefaults>(EMPTY_DEFAULTS);
  const loading = ref(false);
  const lastError = ref<string | null>(null);
  /** Explizites Loaded-Flag — robuster als updated_at-Proxy (Gemini MEDIUM #5). */
  const hasLoadedOnce = ref(false);

  const globalDefault = computed(() => defaults.value.global_default);
  const stageOverrides = computed(() => defaults.value.stage_overrides);

  function effectiveRouteForStage(stageId: StageId): LlmRoute {
    return defaults.value.stage_overrides[stageId] ?? defaults.value.global_default;
  }

  async function load(): Promise<void> {
    loading.value = true;
    lastError.value = null;
    try {
      defaults.value = await getRoutingDefaults();
      hasLoadedOnce.value = true;
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : String(err);
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function setGlobalDefault(route: LlmRoute): Promise<void> {
    lastError.value = null;
    try {
      defaults.value = await replaceGlobalDefault(route);
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : String(err);
      throw err;
    }
  }

  async function setStageOverride(
    stageId: StageId,
    route: LlmRoute | null,
  ): Promise<void> {
    lastError.value = null;
    try {
      defaults.value = await patchRoutingDefaultStage(stageId, route);
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : String(err);
      throw err;
    }
  }

  async function replaceAll(payload: WorkspaceLlmRoutingDefaults): Promise<void> {
    lastError.value = null;
    try {
      defaults.value = await replaceRoutingDefaults(payload);
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : String(err);
      throw err;
    }
  }

  function clearStageOverride(stageId: StageId): Promise<void> {
    return setStageOverride(stageId, null);
  }

  return {
    defaults,
    loading,
    lastError,
    hasLoadedOnce,
    globalDefault,
    stageOverrides,
    effectiveRouteForStage,
    load,
    setGlobalDefault,
    setStageOverride,
    replaceAll,
    clearStageOverride,
  };
});

// ---------------------------------------------------------------------------
// Facade — gebündelter Zugriff auf die drei Teil-Stores
// ---------------------------------------------------------------------------

/**
 * useAiModelsStore — Facade über die konsolidierte AI-Modell-Domäne.
 *
 * Gibt die drei Teil-Stores (providers, profiles, routingDefaults) gebündelt
 * zurück, damit neue Aufrufstellen eine einzige Einstiegs-API haben statt drei
 * separate ``useLlm*Store``-Hooks zu importieren. Die Teil-Stores bleiben
 * einzeln exportiert (Backcompat für bestehende Views + Tests).
 */
export function useAiModelsStore() {
  return {
    providers: useLlmProvidersStore(),
    profiles: useLlmProfilesStore(),
    routingDefaults: useLlmRoutingDefaultsStore(),
  };
}
