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
import {
  defaultRuntimeModelForProvider,
  isRuntimeModelForProvider,
  runtimeModelOptionsForProvider,
  type RuntimeProvider,
} from './useRuntimeLlmOptions'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const STORAGE_MODEL = 'agora.lastModel'
export const STORAGE_CUSTOM_MODEL = 'agora.lastCustomModel'
export const STORAGE_LANG = 'agora.agentLanguage'

export function storedEffectiveModel(
  modelKey = STORAGE_MODEL,
  customModelKey = STORAGE_CUSTOM_MODEL,
): string | null {
  try {
    const stored = localStorage.getItem(modelKey)
    if (!stored || stored === 'default') return null
    if (stored === 'custom') {
      return (localStorage.getItem(customModelKey) || '').trim() || null
    }
    return stored
  } catch {
    return null
  }
}

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
  /** Runtime provider override; when active, model options must match that provider. */
  runtimeProvider?: Ref<RuntimeProvider>
}

export interface UseEnvFormReturn {
  ollamaModels: Ref<ModelPreset[]>
  presetModels: Ref<ModelPreset[]>
  defaultModel: Ref<string>
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

function _loadStoredModel(): string {
  try {
    return localStorage.getItem(STORAGE_MODEL) || 'default'
  } catch {
    return 'default'
  }
}

function _loadStoredCustomModel(): string {
  try {
    return localStorage.getItem(STORAGE_CUSTOM_MODEL) || ''
  } catch {
    return ''
  }
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useEnvForm({ t, onError, runtimeProvider }: UseEnvFormOptions): UseEnvFormReturn {
  // --- State ---

  const ollamaModels = ref<ModelPreset[]>([])
  const presetModels = ref<ModelPreset[]>([])
  const defaultModel = ref<string>('')
  const ollamaReachable = ref<boolean>(false)
  const agentToolsEnabled = ref<boolean>(false)
  const maxToolCallsPerAction = ref<number>(2)
  const loadingModels = ref<boolean>(true)
  const modelOption = ref<string>(_loadStoredModel())
  const customModel = ref<string>(_loadStoredCustomModel())
  const language = ref<string>(_loadStoredLang())

  // --- Computed ---

  const modelOptions = computed<ModelOption[]>(() => {
    if (runtimeProvider?.value && runtimeProvider.value !== 'default') {
      const providerModels = runtimeModelOptionsForProvider(runtimeProvider.value)
      return [
        ...providerModels,
        { value: 'custom', label: t('step2.model.customGroup') },
      ]
    }
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

  // --- LocalStorage persistence ---

  watch(modelOption, (val) => {
    try {
      localStorage.setItem(STORAGE_MODEL, val)
    } catch {
      // ignore — storage may be unavailable in some environments
    }
  })

  watch(customModel, (val) => {
    try {
      localStorage.setItem(STORAGE_CUSTOM_MODEL, val)
    } catch {
      // ignore — storage may be unavailable in some environments
    }
  })

  watch(language, (val) => {
    try {
      localStorage.setItem(STORAGE_LANG, val)
    } catch {
      // ignore
    }
  })

  if (runtimeProvider) {
    watch(runtimeProvider, (provider, previousProvider) => {
      const providerDefault = defaultRuntimeModelForProvider(provider)
      if (provider !== 'default') {
        if (
          modelOption.value !== 'custom' &&
          !isRuntimeModelForProvider(provider, modelOption.value)
        ) {
          modelOption.value = providerDefault || 'custom'
        }
        return
      }
      if (previousProvider && isRuntimeModelForProvider(previousProvider, modelOption.value)) {
        modelOption.value = 'default'
      }
    }, { immediate: true })
  }

  // --- Actions ---

  async function loadModels(): Promise<void> {
    loadingModels.value = true
    try {
      // reason: service interceptor returns raw envelope body at runtime
      const res = (await getAvailableModels()) as unknown as {
        success?: boolean
        data?: {
          ollama?: ModelPreset[]
          presets?: ModelPreset[]
          current_default?: string
          ollama_reachable?: boolean
          agent_tools_enabled?: boolean
          max_tool_calls_per_action?: number
          default_language?: string
        }
      }
      if (res?.success) {
        ollamaModels.value = res.data?.ollama || []
        presetModels.value = res.data?.presets || []
        defaultModel.value = res.data?.current_default || ''
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
        // Restore persisted model selection if it still exists in the new list.
        const stored = (() => {
          try {
            return localStorage.getItem(STORAGE_MODEL)
          } catch {
            return null
          }
        })()
        const runtimeProviderActive = runtimeProvider?.value && runtimeProvider.value !== 'default'
        const storedMatchesRuntimeProvider = runtimeProviderActive
          ? (stored === 'custom' || isRuntimeModelForProvider(runtimeProvider.value, stored || ''))
          : false
        if (
          stored &&
          (runtimeProviderActive
            ? storedMatchesRuntimeProvider
            : (stored === 'default' ||
              stored === 'custom' ||
              presetModels.value.some((p) => p.name === stored) ||
              ollamaModels.value.some((p) => p.name === stored)))
        ) {
          modelOption.value = stored
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
