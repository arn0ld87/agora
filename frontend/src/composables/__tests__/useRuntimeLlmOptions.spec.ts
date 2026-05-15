import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import {
  defaultRuntimeModelForProvider,
  runtimeModelOptionsForProvider,
  runtimeLlmPayloadFromStorage,
  runtimeProviderMissingApiKeyFromStorage,
  SESSION_LLM_API_KEY,
  STORAGE_LLM_BASE_URL,
  STORAGE_LLM_PROVIDER,
} from '../useRuntimeLlmOptions'

describe('runtimeLlmPayloadFromStorage', () => {
  function makeStorageStub(): Storage {
    const store: Record<string, string> = {}
    return {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v
      },
      removeItem: (k: string) => {
        delete store[k]
      },
      clear: () => {
        Object.keys(store).forEach((k) => delete store[k])
      },
      get length() {
        return Object.keys(store).length
      },
      key: (i: number) => Object.keys(store)[i] ?? null,
    }
  }

  beforeEach(() => {
    vi.stubGlobal('localStorage', makeStorageStub())
    vi.stubGlobal('sessionStorage', makeStorageStub())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('liefert null für Server-Default', () => {
    localStorage.setItem(STORAGE_LLM_PROVIDER, 'default')

    expect(runtimeLlmPayloadFromStorage()).toBeNull()
  })

  it('baut Google-Gemini Runtime-Payload mit Default-Base-URL', () => {
    localStorage.setItem(STORAGE_LLM_PROVIDER, 'google')
    sessionStorage.setItem(SESSION_LLM_API_KEY, 'gemini-key')

    expect(runtimeLlmPayloadFromStorage()).toEqual({
      provider: 'google',
      api_key: 'gemini-key',
      base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    })
  })

  it('liest API-Key nur aus sessionStorage — kein Key sendet Provider ohne api_key (DB-Fallback)', () => {
    // Smoke-Fix Slice 04: runtimeLlmPayloadFromStorage() gibt Provider auch ohne Session-Key zurück.
    // Backend löst Key via Settings-DB auf. api_key im localStorage wird ignoriert.
    localStorage.setItem(STORAGE_LLM_PROVIDER, 'custom_openai')
    localStorage.setItem(STORAGE_LLM_BASE_URL, 'https://example.test/v1')
    localStorage.setItem(SESSION_LLM_API_KEY, 'wrong-place')

    // Payload enthält Provider + base_url, aber KEIN api_key (falsch platzierter Key wird ignoriert)
    const payload = runtimeLlmPayloadFromStorage()
    expect(payload).not.toBeNull()
    expect(payload?.provider).toBe('custom_openai')
    expect(payload?.api_key).toBeUndefined()
    // runtimeProviderMissingApiKeyFromStorage: sessionStorage hat keinen Key → true
    expect(runtimeProviderMissingApiKeyFromStorage()).toBe(true)
  })

  it('liefert Gemini-Modelloptionen für den Google-Provider', () => {
    const options = runtimeModelOptionsForProvider('google')

    expect(options.map((option) => option.value)).toContain('gemini-3-flash-preview')
    expect(options.map((option) => option.value)).toContain('gemini-3.1-pro-preview')
    expect(options.map((option) => option.value)).toContain('gemini-2.5-flash')
    expect(defaultRuntimeModelForProvider('google')).toBe('gemini-3-flash-preview')
  })
})
