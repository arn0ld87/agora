import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import type { LlmRuntimePayload } from '../api/llmRuntime'
import { checkLlmProviderHasKey } from '../api/llmProviderKeys'

export const STORAGE_LLM_PROVIDER = 'agora.runtimeLlm.provider'
export const STORAGE_LLM_BASE_URL = 'agora.runtimeLlm.baseUrl'
export const SESSION_LLM_API_KEY = 'agora.runtimeLlm.apiKey'

export type RuntimeProvider = 'default' | 'google' | 'openai' | 'custom_openai'

/** Map frontend runtime provider id → backend provider registry id.
 *  Backend kennt ``openai_compatible``, Frontend nennt das ``custom_openai``.
 *  Fix für Copilot-Comment auf PR #466 (Step2EnvSetup.vue:67). */
export function mapRuntimeProviderToBackendId(provider: RuntimeProvider | string): string {
  if (provider === 'custom_openai') return 'openai_compatible'
  return provider
}

interface Option {
  value: RuntimeProvider
  label: string
}

interface RuntimeModelOption {
  value: string
  label: string
}

export interface UseRuntimeLlmOptionsReturn {
  runtimeProvider: Ref<RuntimeProvider>
  runtimeApiKey: Ref<string>
  runtimeBaseUrl: Ref<string>
  runtimeProviderOptions: ComputedRef<Option[]>
  runtimeProviderEnabled: ComputedRef<boolean>
  runtimePayload: () => LlmRuntimePayload | null
  /** True wenn Provider != default und kein expliziter Key im Sitzungsspeicher. */
  runtimeApiKeyMissing: ComputedRef<boolean>
}

const DEFAULT_BASE_URLS: Record<Exclude<RuntimeProvider, 'default'>, string> = {
  google: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  openai: 'https://api.openai.com/v1',
  custom_openai: '',
}

export const GOOGLE_GEMINI_MODEL_OPTIONS: RuntimeModelOption[] = [
  { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview (Google)' },
  { value: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro Preview (Google)' },
  { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite (Google)' },
  { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro (Google)' },
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash (Google)' },
  { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash-Lite (Google)' },
]

export function runtimeModelOptionsForProvider(provider: RuntimeProvider | string): RuntimeModelOption[] {
  if (provider === 'google') return GOOGLE_GEMINI_MODEL_OPTIONS
  return []
}

export function defaultRuntimeModelForProvider(provider: RuntimeProvider | string): string | null {
  return runtimeModelOptionsForProvider(provider)[0]?.value ?? null
}

export function isRuntimeModelForProvider(provider: RuntimeProvider | string, model: string): boolean {
  return runtimeModelOptionsForProvider(provider).some((option) => option.value === model)
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
  const storedBaseUrl = safeLocalGet(STORAGE_LLM_BASE_URL).trim()
  const baseUrl = storedBaseUrl || defaultBaseUrl(provider)
  // Kein Session-Key → Provider ohne api_key senden; Backend löst via Settings-DB auf.
  return { provider, ...(apiKey ? { api_key: apiKey } : {}), ...(baseUrl ? { base_url: baseUrl } : {}) }
}

export function runtimeProviderMissingApiKeyFromStorage(): boolean {
  const provider = normalizeProvider(safeLocalGet(STORAGE_LLM_PROVIDER, 'default'))
  return provider !== 'default' && !safeSessionGet(SESSION_LLM_API_KEY).trim()
}

/**
 * Liefert ``true`` wenn weder ein Session-Key vorliegt NOCH ein DB-Key in
 * Settings → LLM-Anbieter hinterlegt ist. Für Step 3 / Report-Resume nötig,
 * weil Slice-04-DB-Fallback sonst durch den Storage-only-Guard blockiert
 * wird (Copilot PR #466 auf useRuntimeLlmOptions.ts:108).
 */
export async function runtimeProviderMissingKeyEverywhere(): Promise<boolean> {
  const provider = normalizeProvider(safeLocalGet(STORAGE_LLM_PROVIDER, 'default'))
  if (provider === 'default') return false
  if (safeSessionGet(SESSION_LLM_API_KEY).trim()) return false
  const backendProviderId = mapRuntimeProviderToBackendId(provider)
  const hasDbKey = await checkLlmProviderHasKey(backendProviderId)
  return !hasDbKey
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
    const baseUrl = runtimeBaseUrl.value.trim() || defaultBaseUrl(runtimeProvider.value)
    // Wenn kein expliziter Session-Key vorhanden: Provider ohne api_key senden —
    // Backend löst den Key via SecretResolver aus der Settings-DB auf (Smoke-Fix Slice 04).
    return {
      provider: runtimeProvider.value,
      ...(apiKey ? { api_key: apiKey } : {}),
      ...(baseUrl ? { base_url: baseUrl } : {}),
    }
  }

  const runtimeApiKeyMissing = computed(
    () => runtimeProvider.value !== 'default' && !runtimeApiKey.value.trim(),
  )

  return {
    runtimeProvider,
    runtimeApiKey,
    runtimeBaseUrl,
    runtimeProviderOptions,
    runtimeProviderEnabled,
    runtimePayload,
    runtimeApiKeyMissing,
  }
}
