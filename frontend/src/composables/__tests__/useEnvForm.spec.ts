/**
 * Tests für useEnvForm — Sub-Slice 37, Refs #203.
 *
 * Getestete Contracts:
 *   1. effectiveModel()-Branches: 'default', Preset, 'custom'.
 *   2. modelOptions-computed: enthält Default, Presets, Ollama-Modelle, Custom.
 *   3. loadModels() Erfolg: setzt ollamaModels, ollamaReachable=true, loadingModels=false.
 *   4. loadModels() Fehler: setzt ollamaReachable=false, loadingModels=false, ruft onError auf.
 *   5. localStorage-Persistence Sprache: beim Mount geladen, Änderung schreibt zurück.
 *   6. localStorage-Persistence Modellauswahl: überlebt Mount-Cycle.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import { useEnvForm, STORAGE_CUSTOM_MODEL, STORAGE_MODEL, STORAGE_LANG } from '../useEnvForm'
import type { RuntimeProvider } from '../useRuntimeLlmOptions'

// ---------------------------------------------------------------------------
// Mock t() — identity function; tests check key suffixes, not translated text
// ---------------------------------------------------------------------------

const t = (key: string): string => key

// ---------------------------------------------------------------------------
// Mock API module
// ---------------------------------------------------------------------------

vi.mock('../../api/simulation', () => ({
  getAvailableModels: vi.fn(),
}))

import { getAvailableModels } from '../../api/simulation'
const mockedGetAvailableModels = vi.mocked(getAvailableModels)

// ---------------------------------------------------------------------------
// LocalStorage stub
// ---------------------------------------------------------------------------

function makeLocalStorageStub(): Storage {
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

let localStorageStub: Storage

beforeEach(() => {
  localStorageStub = makeLocalStorageStub()
  vi.stubGlobal('localStorage', localStorageStub)
  mockedGetAvailableModels.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useEnvForm', () => {
  // -------------------------------------------------------------------------
  // Case 1 — effectiveModel()-Branches
  // -------------------------------------------------------------------------

  describe('Case 1 — effectiveModel()-Branches', () => {
    it('modelOption=default → effectiveModel() liefert null', () => {
      const f = useEnvForm({ t })
      f.modelOption.value = 'default'
      expect(f.effectiveModel()).toBeNull()
    })

    it('modelOption=<preset-name> → effectiveModel() liefert den Preset-Namen', () => {
      const f = useEnvForm({ t })
      f.modelOption.value = 'llama3'
      expect(f.effectiveModel()).toBe('llama3')
    })

    it('modelOption=custom + customModel gesetzt → effectiveModel() liefert customModel', () => {
      const f = useEnvForm({ t })
      f.modelOption.value = 'custom'
      f.customModel.value = 'my-model:latest'
      expect(f.effectiveModel()).toBe('my-model:latest')
    })

    it('modelOption=custom + customModel leer → effectiveModel() liefert null', () => {
      const f = useEnvForm({ t })
      f.modelOption.value = 'custom'
      f.customModel.value = '   '
      expect(f.effectiveModel()).toBeNull()
    })
  })

  // -------------------------------------------------------------------------
  // Case 2 — modelOptions-computed
  // -------------------------------------------------------------------------

  describe('Case 2 — modelOptions-computed', () => {
    it('enthält Default-Eintrag, Presets, Ollama-Modelle (ohne Preset-Duplikate) und Custom', () => {
      const f = useEnvForm({ t })
      f.defaultModel.value = 'qwen3'
      f.presetModels.value = [{ name: 'gemma3', label: 'Gemma 3' }]
      f.ollamaModels.value = [
        { name: 'gemma3', label: 'Gemma 3' }, // duplicate with preset — must be skipped
        { name: 'llama3', label: 'Llama 3' },
      ]

      const opts = f.modelOptions.value

      // Default entry
      const def = opts.find((o) => o.value === 'default')
      expect(def).toBeTruthy()
      expect(def!.label).toContain('qwen3')

      // Preset entry
      const gemma = opts.find((o) => o.value === 'gemma3')
      expect(gemma).toBeTruthy()
      expect(gemma!.label).toBe('Gemma 3')

      // Ollama-only (not in presets) entry
      const llama = opts.find((o) => o.value === 'llama3')
      expect(llama).toBeTruthy()
      expect(llama!.label).toContain('Ollama')

      // Gemma3 appears only once (preset wins, Ollama-duplicate skipped)
      expect(opts.filter((o) => o.value === 'gemma3')).toHaveLength(1)

      // Custom entry
      const custom = opts.find((o) => o.value === 'custom')
      expect(custom).toBeTruthy()
    })

    it('leere Presets + leere Ollama → nur Default + Custom', () => {
      const f = useEnvForm({ t })
      f.defaultModel.value = ''
      f.presetModels.value = []
      f.ollamaModels.value = []

      const opts = f.modelOptions.value
      expect(opts).toHaveLength(2)
      expect(opts[0].value).toBe('default')
      expect(opts[1].value).toBe('custom')
    })

    it('zeigt bei Google-Runtime-Provider Gemini-Modelle statt Ollama-Modelle', async () => {
      localStorage.setItem(STORAGE_MODEL, 'gemma3:31b')
      const runtimeProvider = ref<RuntimeProvider>('google')
      const f = useEnvForm({ t, runtimeProvider })
      f.defaultModel.value = 'gemma3:31b'
      f.ollamaModels.value = [{ name: 'gemma3:31b', label: 'Gemma 3 31B' }]

      await nextTick()

      const opts = f.modelOptions.value
      expect(opts.map((o) => o.value)).toContain('gemini-3-flash-preview')
      expect(opts.map((o) => o.value)).toContain('gemini-2.5-flash')
      expect(opts.map((o) => o.value)).not.toContain('gemma3:31b')
      expect(f.modelOption.value).toBe('gemini-3-flash-preview')
    })
  })

  // -------------------------------------------------------------------------
  // Case 3 — loadModels() Erfolg
  // -------------------------------------------------------------------------

  describe('Case 3 — loadModels() Erfolg', () => {
    it('setzt ollamaModels, ollamaReachable=true, loadingModels=false nach Erfolg', async () => {
      mockedGetAvailableModels.mockResolvedValue({
        success: true,
        data: {
          ollama: [{ name: 'llama3', label: 'Llama 3' }],
          presets: [{ name: 'gemma3', label: 'Gemma 3' }],
          current_default: 'gemma3',
          ollama_reachable: true,
          agent_tools_enabled: false,
          max_tool_calls_per_action: 3,
        },
      } as never)

      const f = useEnvForm({ t })
      await f.loadModels()

      expect(f.ollamaModels.value).toEqual([{ name: 'llama3', label: 'Llama 3' }])
      expect(f.presetModels.value).toEqual([{ name: 'gemma3', label: 'Gemma 3' }])
      expect(f.defaultModel.value).toBe('gemma3')
      expect(f.ollamaReachable.value).toBe(true)
      expect(f.agentToolsEnabled.value).toBe(false)
      expect(f.maxToolCallsPerAction.value).toBe(3)
      expect(f.loadingModels.value).toBe(false)
    })

    it('setzt language aus default_language wenn STORAGE_LANG noch nicht gesetzt', async () => {
      mockedGetAvailableModels.mockResolvedValue({
        success: true,
        data: {
          ollama: [],
          presets: [],
          current_default: '',
          ollama_reachable: false,
          agent_tools_enabled: false,
          max_tool_calls_per_action: 2,
          default_language: 'en',
        },
      } as never)

      // localStorage has no STORAGE_LANG key → composable reads 'de' default
      const f = useEnvForm({ t })
      expect(f.language.value).toBe('de')

      await f.loadModels()
      // Backend says 'en' and localStorage was empty → adopt backend language
      expect(f.language.value).toBe('en')
    })

    it('behält vorhandene language wenn STORAGE_LANG gesetzt ist', async () => {
      localStorageStub.setItem(STORAGE_LANG, 'de')
      mockedGetAvailableModels.mockResolvedValue({
        success: true,
        data: {
          ollama: [],
          presets: [],
          current_default: '',
          ollama_reachable: false,
          agent_tools_enabled: false,
          max_tool_calls_per_action: 2,
          default_language: 'en',
        },
      } as never)

      const f = useEnvForm({ t })
      expect(f.language.value).toBe('de')

      await f.loadModels()
      // STORAGE_LANG already set to 'de' → don't override with backend 'en'
      expect(f.language.value).toBe('de')
    })

    it('restauriert persistierten modelOption wenn er noch in der neuen Liste ist', async () => {
      localStorageStub.setItem(STORAGE_MODEL, 'gemma3')
      mockedGetAvailableModels.mockResolvedValue({
        success: true,
        data: {
          ollama: [],
          presets: [{ name: 'gemma3', label: 'Gemma 3' }],
          current_default: 'gemma3',
          ollama_reachable: true,
          agent_tools_enabled: false,
          max_tool_calls_per_action: 2,
        },
      } as never)

      const f = useEnvForm({ t })
      // Composable initially reads stored 'gemma3'
      expect(f.modelOption.value).toBe('gemma3')

      await f.loadModels()
      // Still 'gemma3' because it exists in presets
      expect(f.modelOption.value).toBe('gemma3')
    })
  })

  // -------------------------------------------------------------------------
  // Case 4 — loadModels() Fehler
  // -------------------------------------------------------------------------

  describe('Case 4 — loadModels() Fehler', () => {
    it('setzt ollamaReachable=false, loadingModels=false und ruft onError bei Netzwerkfehler', async () => {
      mockedGetAvailableModels.mockRejectedValue(new Error('Network Error'))

      const onError = vi.fn()
      const f = useEnvForm({ t, onError })

      // loadingModels starts as true
      expect(f.loadingModels.value).toBe(true)

      await f.loadModels()

      expect(f.ollamaReachable.value).toBe(false)
      expect(f.loadingModels.value).toBe(false)
      expect(onError).toHaveBeenCalledOnce()
      expect(onError.mock.calls[0][0]).toContain('errors.noLlm')
      expect(onError.mock.calls[0][0]).toContain('Network Error')
    })

    it('kein onError-Crash wenn callback nicht angegeben (optionaler Parameter)', async () => {
      mockedGetAvailableModels.mockRejectedValue(new Error('fail'))
      // No onError provided — must not throw
      const f = useEnvForm({ t })
      await expect(f.loadModels()).resolves.toBeUndefined()
      expect(f.ollamaReachable.value).toBe(false)
      expect(f.loadingModels.value).toBe(false)
    })
  })

  // -------------------------------------------------------------------------
  // Case 5 — localStorage-Persistence Sprache
  // -------------------------------------------------------------------------

  describe('Case 5 — localStorage-Persistence: Sprache', () => {
    it('language wird beim Mount aus localStorage geladen', () => {
      localStorageStub.setItem(STORAGE_LANG, 'en')
      const f = useEnvForm({ t })
      expect(f.language.value).toBe('en')
    })

    it('fällt auf "de" zurück wenn kein localStorage-Eintrag', () => {
      // localStorageStub is empty
      const f = useEnvForm({ t })
      expect(f.language.value).toBe('de')
    })

    it('Änderung von language schreibt in localStorage zurück', async () => {
      const f = useEnvForm({ t })
      f.language.value = 'en'

      await nextTick()
      await nextTick()

      expect(localStorageStub.getItem(STORAGE_LANG)).toBe('en')
    })
  })

  // -------------------------------------------------------------------------
  // Case 6 — localStorage-Persistence Modellauswahl
  // -------------------------------------------------------------------------

  describe('Case 6 — localStorage-Persistence: Modellauswahl', () => {
    it('modelOption wird beim Mount aus localStorage geladen', () => {
      localStorageStub.setItem(STORAGE_MODEL, 'custom')
      const f = useEnvForm({ t })
      expect(f.modelOption.value).toBe('custom')
    })

    it('fällt auf "default" zurück wenn kein localStorage-Eintrag', () => {
      // localStorageStub is empty
      const f = useEnvForm({ t })
      expect(f.modelOption.value).toBe('default')
    })

    it('Änderung von modelOption schreibt in localStorage zurück', async () => {
      const f = useEnvForm({ t })
      f.modelOption.value = 'llama3'

      await nextTick()
      await nextTick()

      expect(localStorageStub.getItem(STORAGE_MODEL)).toBe('llama3')
    })

    it('Modellauswahl überlebt Mount-Cycle (neues Composable liest persistierten Wert)', async () => {
      const f1 = useEnvForm({ t })
      f1.modelOption.value = 'gemma3'

      await nextTick()
      await nextTick()

      // Simulate new mount by creating a new composable instance
      const f2 = useEnvForm({ t })
      expect(f2.modelOption.value).toBe('gemma3')
    })

    it('customModel wird persistiert und beim nächsten Mount wieder geladen', async () => {
      const f1 = useEnvForm({ t })
      f1.modelOption.value = 'custom'
      f1.customModel.value = 'deepseek-v3.2:cloud'

      await nextTick()
      await nextTick()

      expect(localStorageStub.getItem(STORAGE_CUSTOM_MODEL)).toBe('deepseek-v3.2:cloud')

      const f2 = useEnvForm({ t })
      expect(f2.modelOption.value).toBe('custom')
      expect(f2.customModel.value).toBe('deepseek-v3.2:cloud')
      expect(f2.effectiveModel()).toBe('deepseek-v3.2:cloud')
    })
  })
})
