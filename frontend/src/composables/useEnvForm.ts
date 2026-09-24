/**
 * useEnvForm — Composable for Language + Runtime-Metadata of Step 2 (Sub-Slice 37, Refs #203).
 *
 * Extracted from Step2EnvSetup.vue (lines 38–115) to reduce that component below 800 LOC.
 *
 * Owns:
 *   - ollamaModels ref (list of installed Ollama models)
 *   - presetModels ref (curated preset list from backend)
 *   - defaultModel ref (current_default from backend)
 *   - ollamaReachable ref (connectivity flag)
 *   - agentToolsEnabled ref (feature flag from backend)
 *   - maxToolCallsPerAction ref
 *   - loadingModels ref
 *   - language ref ('de' | 'en' | ...)
 *   - loadModels() action
 *
 * Keine Modellwahl: die kanonische Senke ist Step2EnvSetup.selectedModelRef
 * (AiModelRef via AiModelPicker). Die fruehere Modellwahl-API ist entfernt (#903).
 *
 * localStorage-Keys are exported as constants for tests and sibling modules.
 *
 * The `t` function and optional `onError` callback are injected so this
 * composable can be tested without a vue-i18n provider.
 */

import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { getAvailableModels, type ModelPreset } from '../api/simulation'

// Der Preset-Typ gehoert dem API-Vertrag; hier stand bis zum Review von
// PR #1390 eine zweite, driftfaehige Kopie. Re-Export, weil `ModelPreset`
// Teil der oeffentlichen Signatur von `UseEnvFormReturn` ist.
export type { ModelPreset }

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const STORAGE_LANG = 'agora.agentLanguage'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseEnvFormOptions {
  /** vue-i18n t() injected so tests don't need a provider. */
  t: (key: string, params?: Record<string, unknown>) => string
  /** Called when loadModels() encounters a network/API error. */
  onError?: (msg: string) => void
}

export interface UseEnvFormReturn {
  ollamaModels: Ref<ModelPreset[]>
  presetModels: Ref<ModelPreset[]>
  defaultModel: Ref<string>
  /** Vokabular deckungsgleich mit HttpDetectedProvider (registry.py); bewusst
   * `string` statt Enum, siehe contracts/modelPresetContract.ts. */
  defaultProvider: Ref<string>
  serverDefaultRequiresOllama: ComputedRef<boolean>
  ollamaReachable: Ref<boolean>
  agentToolsEnabled: Ref<boolean>
  maxToolCallsPerAction: Ref<number>
  loadingModels: Ref<boolean>
  language: Ref<string>
  loadModels: () => Promise<void>
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

function _loadStoredLang(): string {
  try {
    return localStorage.getItem(STORAGE_LANG) || 'de'
  } catch {
    return 'de'
  }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useEnvForm({ t, onError }: UseEnvFormOptions): UseEnvFormReturn {
  // --- State ---

  const ollamaModels = ref<ModelPreset[]>([])
  const presetModels = ref<ModelPreset[]>([])
  const defaultModel = ref<string>('')
  const defaultProvider = ref<string>('unknown')
  const serverDefaultRequiresOllama = computed<boolean>(() => defaultProvider.value === 'ollama')
  const ollamaReachable = ref<boolean>(false)
  const agentToolsEnabled = ref<boolean>(false)
  const maxToolCallsPerAction = ref<number>(2)
  const loadingModels = ref<boolean>(true)
  const language = ref<string>(_loadStoredLang())

  watch(language, (val) => {
    try {
      localStorage.setItem(STORAGE_LANG, val)
    } catch {
      // ignore
    }
  })

  // --- Actions ---

  async function loadModels(): Promise<void> {
    loadingModels.value = true
    try {
      // Kein Cast mehr noetig: getAvailableModels deklariert die Envelope
      // und AvailableModelsResponse die Felder, die der Endpunkt wirklich
      // liefert.
      const res = await getAvailableModels()
      if (res?.success) {
        ollamaModels.value = res.data?.ollama || []
        presetModels.value = res.data?.presets || []
        defaultModel.value = res.data?.current_default || ''
        defaultProvider.value = res.data?.default_provider || 'unknown'
        ollamaReachable.value = !!res.data?.ollama_reachable
        agentToolsEnabled.value = !!res.data?.agent_tools_enabled
        maxToolCallsPerAction.value = res.data?.max_tool_calls_per_action || 2
        if (res.data?.default_language) {
          try {
            if (!localStorage.getItem(STORAGE_LANG)) {
              language.value = res.data.default_language
            }
          } catch {
            language.value = res.data.default_language
          }
        }
      }
    } catch (e) {
      const err = e as { message?: string }
      const msg = t('errors.noLlm') + ' (' + (err.message ?? '') + ')'
      onError?.(msg)
      ollamaReachable.value = false
    } finally {
      loadingModels.value = false
    }
  }

  return {
    ollamaModels,
    presetModels,
    defaultModel,
    defaultProvider,
    serverDefaultRequiresOllama,
    ollamaReachable,
    agentToolsEnabled,
    maxToolCallsPerAction,
    loadingModels,
    language,
    loadModels,
  }
}
