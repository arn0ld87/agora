/**
 * useEnvForm — Composable for Model/Language/Agent-Tools-Config state (Sub-Slice 37, Refs #203).
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
 *   - modelOption ref ('default' | preset name | 'custom')
 *   - customModel ref (model name string when modelOption === 'custom')
 *   - language ref ('de' | 'en' | ...)
 *   - modelOptions computed (option list for Select component)
 *   - loadModels() action
 *   - effectiveModel() helper
 *
 * localStorage-Keys are exported as constants for tests and sibling modules.
 *
 * The `t` function and optional `onError` callback are injected so this
 * composable can be tested without a vue-i18n provider.
 */

import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { getAvailableModels } from '../api/simulation'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const STORAGE_LANG = 'agora.agentLanguage'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ModelPreset {
  name: string
  label?: string
}

export interface ModelOption {
  value: string
  label: string
}

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
  defaultProvider: Ref<'ollama' | 'cloud' | 'openai' | 'unknown'>
  serverDefaultRequiresOllama: ComputedRef<boolean>
  ollamaReachable: Ref<boolean>
  agentToolsEnabled: Ref<boolean>
  maxToolCallsPerAction: Ref<number>
  loadingModels: Ref<boolean>
  modelOption: Ref<string>
  customModel: Ref<string>
  language: Ref<string>
  modelOptions: ComputedRef<ModelOption[]>
  loadModels: () => Promise<void>
  effectiveModel: () => string | null
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
  const defaultProvider = ref<'ollama' | 'cloud' | 'openai' | 'unknown'>('unknown')
  const serverDefaultRequiresOllama = computed<boolean>(() => defaultProvider.value === 'ollama')
  const ollamaReachable = ref<boolean>(false)
  const agentToolsEnabled = ref<boolean>(false)
  const maxToolCallsPerAction = ref<number>(2)
  const loadingModels = ref<boolean>(true)
  const modelOption = ref<string>('default')
  const customModel = ref<string>('')
  const language = ref<string>(_loadStoredLang())

  // --- Computed ---

  const modelOptions = computed<ModelOption[]>(() => {
    const opts: ModelOption[] = []
    opts.push({
      value: 'default',
      label: `${t('step2.model.default')} — ${defaultModel.value || '?'}`,
    })
    for (const p of presetModels.value) {
      opts.push({ value: p.name, label: p.label || p.name })
    }
    for (const m of ollamaModels.value) {
      if (presetModels.value.some((p) => p.name === m.name)) continue
      opts.push({ value: m.name, label: `${m.label || m.name} (Ollama)` })
    }
    opts.push({ value: 'custom', label: t('step2.model.customGroup') })
    return opts
  })

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

  function effectiveModel(): string | null {
    if (modelOption.value === 'default') return null
    if (modelOption.value === 'custom') return customModel.value.trim() || null
    return modelOption.value
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
    modelOption,
    customModel,
    language,
    modelOptions,
    loadModels,
    effectiveModel,
  }
}
