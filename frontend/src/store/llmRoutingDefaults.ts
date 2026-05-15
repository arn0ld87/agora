/**
 * llmRoutingDefaults — Pinia-Store für Workspace-weite LLM-Defaults.
 *
 * Hält die globale Default-Route (z. B. "openai gpt-4o-mini") plus optionale
 * Stage-Overrides (z. B. "Report-Stage nutzt gpt-4o"). Wird beim Run-Start
 * vom Backend in die runspezifische `RuntimeLlmRouting` gemergt.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  getRoutingDefaults,
  patchRoutingDefaultStage,
  replaceGlobalDefault,
  replaceRoutingDefaults,
} from "../api/llmRoutingDefaults";
import type { StageId, StageLLMRoute } from "../contracts/llmRoutingContract";
import type { WorkspaceLlmRoutingDefaults } from "../contracts/workspaceRoutingContract";

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

  function effectiveRouteForStage(stageId: StageId): StageLLMRoute {
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

  async function setGlobalDefault(route: StageLLMRoute): Promise<void> {
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
    route: StageLLMRoute | null,
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
