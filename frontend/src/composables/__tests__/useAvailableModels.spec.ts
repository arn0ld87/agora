/**
 * useAvailableModels — Unit-Tests
 *
 * Mockt listLlmProviders und listProviderModels aus @/api/llmRouting.
 * Prüft: Sortierung, Cache, Fehlerbehandlung, Schema-Filterung.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'

// ---------------------------------------------------------------------------
// Mock BEFORE import of composable (vi.mock hoisted)
// ---------------------------------------------------------------------------
vi.mock('@/api/llmRouting', () => ({
  listLlmProviders: vi.fn(),
  listProviderModels: vi.fn(),
}))

import { listLlmProviders, listProviderModels } from '@/api/llmRouting'
import { useAvailableModels } from '../useAvailableModels'

const mockListProviders = vi.mocked(listLlmProviders)
const mockListModels = vi.mocked(listProviderModels)

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const providerOllama = {
  id: 'ollama',
  label: 'Ollama',
  type: 'ollama_cloud' as const,
  base_url: 'http://localhost:11434',
  api_key_ref: null,
  supports_models_endpoint: true,
  fallback_models: [],
}

const providerGoogle = {
  id: 'google',
  label: 'Google Gemini',
  type: 'google' as const,
  base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  api_key_ref: 'google_key',
  supports_models_endpoint: true,
  fallback_models: [],
}

const providerNoEndpoint = {
  id: 'noop',
  label: 'NoEndpoint',
  type: 'openai' as const,
  base_url: null,
  api_key_ref: null,
  supports_models_endpoint: false,
  fallback_models: [],
}

function makeModelEntry(id: string, providerId: string) {
  return {
    id,
    name: id,
    provider_id: providerId,
    source: 'live' as const,
    refreshed_at: Date.now() / 1000,
  }
}

// ---------------------------------------------------------------------------
describe('useAvailableModels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ---------------------------------------------------------------------------
  it('startet mit loading=true und liefert nach fetch models', async () => {
    mockListProviders.mockResolvedValue([providerOllama] as any)
    mockListModels.mockResolvedValue([
      makeModelEntry('llama3.1:8b', 'ollama'),
      makeModelEntry('qwen2.5:32b', 'ollama'),
    ] as any)

    const { loading, models, error } = useAvailableModels()

    expect(loading.value).toBe(true)
    await vi.runAllTimersAsync()
    await nextTick()

    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
    expect(models.value).toHaveLength(2)
  })

  // ---------------------------------------------------------------------------
  it('sortiert: provider_label ASC (ci), dann model_id ASC (ci)', async () => {
    mockListProviders.mockResolvedValue([providerGoogle, providerOllama] as any)
    mockListModels.mockImplementation(async (id) => {
      if (id === 'google') {
        return [
          makeModelEntry('gemini-2.5-pro', 'google'),
          makeModelEntry('gemini-1.5-flash', 'google'),
        ] as any
      }
      if (id === 'ollama') {
        return [
          makeModelEntry('zephyr:7b', 'ollama'),
          makeModelEntry('llama3.1:8b', 'ollama'),
        ] as any
      }
      return []
    })

    const { models } = useAvailableModels()
    // Alle Promises durchlaufen lassen
    await vi.runAllTimersAsync()
    await nextTick()

    // Google Gemini (G) kommt vor Ollama (O) alphabetisch
    expect(models.value[0].provider_label).toBe('Google Gemini')
    expect(models.value[1].provider_label).toBe('Google Gemini')
    // Innerhalb Google: gemini-1.5-flash < gemini-2.5-pro
    expect(models.value[0].model_id).toBe('gemini-1.5-flash')
    expect(models.value[1].model_id).toBe('gemini-2.5-pro')
    // Ollama kommt danach
    expect(models.value[2].provider_label).toBe('Ollama')
    expect(models.value[3].provider_label).toBe('Ollama')
    // llama < zephyr
    expect(models.value[2].model_id).toBe('llama3.1:8b')
    expect(models.value[3].model_id).toBe('zephyr:7b')
  })

  // ---------------------------------------------------------------------------
  it('überspringt Provider mit supports_models_endpoint === false', async () => {
    mockListProviders.mockResolvedValue([providerOllama, providerNoEndpoint] as any)
    mockListModels.mockResolvedValue([makeModelEntry('llama3.1:8b', 'ollama')] as any)

    const { models } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    // listProviderModels darf nur für 'ollama' aufgerufen werden
    expect(mockListModels).toHaveBeenCalledTimes(1)
    expect(mockListModels).toHaveBeenCalledWith('ollama', 'http://localhost:11434')
    expect(models.value.every((m) => m.provider_id !== 'noop')).toBe(true)
  })

  // ---------------------------------------------------------------------------
  it('setzt error bei Provider-Fetch-Fehler, liefert leere Modellliste', async () => {
    mockListProviders.mockRejectedValue(new Error('Network error'))

    const { models, error, loading } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    expect(loading.value).toBe(false)
    expect(error.value).toContain('Network error')
    expect(models.value).toHaveLength(0)
  })

  // ---------------------------------------------------------------------------
  it('loggt Warnung wenn ein einzelner Provider-Modell-Call fehlschlägt, rest unberührt', async () => {
    mockListProviders.mockResolvedValue([providerOllama, providerGoogle] as any)
    mockListModels.mockImplementation(async (id) => {
      if (id === 'google') throw new Error('Google auth error')
      return [makeModelEntry('llama3.1:8b', 'ollama')] as any
    })

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { models, error } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    // Kein globaler Fehler — nur Warnung
    expect(error.value).toBeNull()
    // Ollama-Modelle sind da
    expect(models.value).toHaveLength(1)
    expect(models.value[0].model_id).toBe('llama3.1:8b')
    // Warnung wurde ausgegeben
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  // ---------------------------------------------------------------------------
  it('nutzt Cache: zweiter refresh-Call triggert keinen neuen API-Call', async () => {
    mockListProviders.mockResolvedValue([providerOllama] as any)
    mockListModels.mockResolvedValue([makeModelEntry('llama3.1:8b', 'ollama')] as any)

    const { refresh } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    // Erster fetch (aus useAvailableModels-Init)
    expect(mockListProviders).toHaveBeenCalledTimes(1)

    // Zweiter refresh — Cache ist frisch (< 5 min), kein API-Call
    await refresh()
    await nextTick()

    expect(mockListProviders).toHaveBeenCalledTimes(1)
  })

  // ---------------------------------------------------------------------------
  it('invalidiert Cache nach 5 Minuten und fetcht erneut', async () => {
    mockListProviders.mockResolvedValue([providerOllama] as any)
    mockListModels.mockResolvedValue([makeModelEntry('llama3.1:8b', 'ollama')] as any)

    const { refresh } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    expect(mockListProviders).toHaveBeenCalledTimes(1)

    // 5 Minuten + 1 ms vorspulen
    vi.advanceTimersByTime(5 * 60 * 1000 + 1)

    await refresh()
    await vi.runAllTimersAsync()
    await nextTick()

    expect(mockListProviders).toHaveBeenCalledTimes(2)
  })

  // ---------------------------------------------------------------------------
  it('verwirft Provider mit ungültigem Zod-Schema graceful', async () => {
    // providers-Antwort mit kaputtem Eintrag (type ungültig)
    const badProvider = { id: 'bad', label: 'Bad', type: 'UNKNOWN_TYPE' }
    mockListProviders.mockResolvedValue([badProvider] as any)

    const { models, error } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    // Schema-Fehler → globaler Fehler
    expect(error.value).not.toBeNull()
    expect(models.value).toHaveLength(0)
  })

  // ---------------------------------------------------------------------------
  it('PickerModel enthält provider_id, provider_label, model_id, model_label, source', async () => {
    mockListProviders.mockResolvedValue([providerOllama] as any)
    mockListModels.mockResolvedValue([
      { id: 'llama3.1:8b', name: 'LLaMA 3.1 8B', provider_id: 'ollama', source: 'live', refreshed_at: 1 },
    ] as any)

    const { models } = useAvailableModels()
    await vi.runAllTimersAsync()
    await nextTick()

    expect(models.value[0]).toMatchObject({
      provider_id: 'ollama',
      provider_label: 'Ollama',
      model_id: 'llama3.1:8b',
      model_label: 'LLaMA 3.1 8B',
      source: 'live',
    })
  })
})
