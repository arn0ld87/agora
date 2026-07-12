/**
 * llmProviders — Pinia-Store für LLM-Provider-Verwaltung.
 *
 * Aggregiert:
 *   - statische Provider-Beschreibungen (GET /api/llm/providers)
 *   - persistierte API-Key-Entries (GET /api/llm/providers/api-keys) — Legacy
 *   - dynamische Modelllisten (GET /api/llm/providers/<id>/models, 10-min-Cache)
 *   - kanonischer Connection-Lifecycle (GET/PUT/DELETE
 *     /api/llm/provider-connections*, Onboarding Slice 3 Task 5)
 *
 * Klartext-Keys laufen ausschließlich durch ``upsertKey``/``upsertConnection``
 * ans Backend und werden hier NIE im State gehalten — `lastError`, `models`,
 * `entries`, `connections` sind die einzigen sichtbaren Daten.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
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
import type { ProviderDescriptor } from "../contracts/llmRoutingContract";
import type { LlmProviderKeyEntry } from "../contracts/llmProviderKeysContract";
import type {
  AiModel,
  ProviderConnection,
  ProviderConnectionTestResult,
} from "../contracts/aiProviderContract";
import service from "../api";
import type { ApiSuccessEnvelope } from "../api/envelope";
import { isApiError } from "../api/envelope";
import { unwrapResponse } from "../api/parse";

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
