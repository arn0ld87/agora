import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { LlmRuntimePayload } from '../api/llmRuntime'

export const STORAGE_LLM_PROVIDER = 'agora.runtimeLlm.provider'
export const STORAGE_LLM_BASE_URL = 'agora.runtimeLlm.baseUrl'
export const SESSION_LLM_API_KEY = 'agora.runtimeLlm.apiKey'

type RuntimeProvider = 'default' | 'google' | 'openai' | 'custom_openai'

interface Option {
  value: RuntimeProvider
  label: string
}

export interface UseRuntimeLlmOptionsReturn {
  runtimeProvider: Ref<RuntimeProvider>
  runtimeApiKey: Ref<string>
  runtimeBaseUrl: Ref<string>
  runtimeProviderOptions: ComputedRef<Option[]>
  runtimeProviderEnabled: ComputedRef<boolean>
  runtimePayload: () => LlmRuntimePayload | null
}

const DEFAULT_BASE_URLS: Record<Exclude<RuntimeProvider, 'default'>, string> = {
  google: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  openai: 'https://api.openai.com/v1',
  custom_openai: '',
}

function safeLocalGet(key: string, fallback = ''): string {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}

function safeLocalSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // ignore
  }
}

function safeSessionGet(key: string, fallback = ''): string {
  try {
    return sessionStorage.getItem(key) || fallback
  } catch {
    return fallback
  }
}

function safeSessionSet(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    // ignore
  }
}

function normalizeProvider(value: string): RuntimeProvider {
  if (value === 'google' || value === 'openai' || value === 'custom_openai') return value
  return 'default'
}

function defaultBaseUrl(provider: RuntimeProvider): string {
  if (provider === 'default') return ''
  return DEFAULT_BASE_URLS[provider]
}

export function runtimeLlmPayloadFromStorage(): LlmRuntimePayload | null {
  const provider = normalizeProvider(safeLocalGet(STORAGE_LLM_PROVIDER, 'default'))
  if (provider === 'default') return null
  const apiKey = safeSessionGet(SESSION_LLM_API_KEY).trim()
  if (!apiKey) return null
  const storedBaseUrl = safeLocalGet(STORAGE_LLM_BASE_URL).trim()
  const baseUrl = storedBaseUrl || defaultBaseUrl(provider)
  return { provider, api_key: apiKey, ...(baseUrl ? { base_url: baseUrl } : {}) }
}

export function runtimeProviderMissingApiKeyFromStorage(): boolean {
  const provider = normalizeProvider(safeLocalGet(STORAGE_LLM_PROVIDER, 'default'))
  return provider !== 'default' && !safeSessionGet(SESSION_LLM_API_KEY).trim()
}

export function useRuntimeLlmOptions(
  t: (key: string) => string,
): UseRuntimeLlmOptionsReturn {
  const runtimeProvider = ref<RuntimeProvider>(
    normalizeProvider(safeLocalGet(STORAGE_LLM_PROVIDER, 'default')),
  )
  const runtimeApiKey = ref(safeSessionGet(SESSION_LLM_API_KEY))
  const runtimeBaseUrl = ref(safeLocalGet(STORAGE_LLM_BASE_URL))

  const runtimeProviderOptions = computed<Option[]>(() => [
    { value: 'default', label: t('step2.runtimeProvider.default') },
    { value: 'google', label: t('step2.runtimeProvider.google') },
    { value: 'openai', label: t('step2.runtimeProvider.openai') },
    { value: 'custom_openai', label: t('step2.runtimeProvider.customOpenAi') },
  ])

  const runtimeProviderEnabled = computed(() => runtimeProvider.value !== 'default')

  watch(runtimeProvider, (provider) => {
    safeLocalSet(STORAGE_LLM_PROVIDER, provider)
    if (provider === 'google' || provider === 'openai') {
      runtimeBaseUrl.value = defaultBaseUrl(provider)
    } else if (provider === 'custom_openai' && Object.values(DEFAULT_BASE_URLS).includes(runtimeBaseUrl.value)) {
      runtimeBaseUrl.value = ''
    }
  })

  watch(runtimeApiKey, (value) => {
    safeSessionSet(SESSION_LLM_API_KEY, value)
  })

  watch(runtimeBaseUrl, (value) => {
    safeLocalSet(STORAGE_LLM_BASE_URL, value)
  })

  function runtimePayload(): LlmRuntimePayload | null {
    if (runtimeProvider.value === 'default') return null
    const apiKey = runtimeApiKey.value.trim()
    if (!apiKey) return null
    const baseUrl = runtimeBaseUrl.value.trim() || defaultBaseUrl(runtimeProvider.value)
    return {
      provider: runtimeProvider.value,
      api_key: apiKey,
      ...(baseUrl ? { base_url: baseUrl } : {}),
    }
  }

  return {
    runtimeProvider,
    runtimeApiKey,
    runtimeBaseUrl,
    runtimeProviderOptions,
    runtimeProviderEnabled,
    runtimePayload,
  }
}
