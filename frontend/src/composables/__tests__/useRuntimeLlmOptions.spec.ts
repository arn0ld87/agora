import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import {
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

  it('liest API-Key nur aus sessionStorage', () => {
    localStorage.setItem(STORAGE_LLM_PROVIDER, 'custom_openai')
    localStorage.setItem(STORAGE_LLM_BASE_URL, 'https://example.test/v1')
    localStorage.setItem(SESSION_LLM_API_KEY, 'wrong-place')

    expect(runtimeLlmPayloadFromStorage()).toBeNull()
    expect(runtimeProviderMissingApiKeyFromStorage()).toBe(true)
  })
})
