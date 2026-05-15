/**
 * llmProviders — Pinia-Store für LLM-Provider-Verwaltung.
 *
 * Aggregiert:
 *   - statische Provider-Beschreibungen (GET /api/llm/providers)
 *   - persistierte API-Key-Entries (GET /api/llm/providers/api-keys)
 *   - dynamische Modelllisten (GET /api/llm/providers/<id>/models, 10-min-Cache)
 *
 * Klartext-Keys laufen ausschließlich durch ``upsertKey`` ans Backend und
 * werden hier NIE im State gehalten — `lastError`, `models`, `entries` sind die
 * einzigen sichtbaren Daten.
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
import { ProviderDescriptor } from "../contracts/llmRoutingContract";
import { LlmProviderKeyEntry } from "../contracts/llmProviderKeysContract";
import service from "../api";
import type { ApiSuccessEnvelope } from "../api/envelope";

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
      const list = (resp as unknown as { data: ModelEntry[] }).data;
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
  };
});
