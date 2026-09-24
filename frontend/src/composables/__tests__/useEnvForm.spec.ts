/**
 * Tests für useEnvForm — Sub-Slice 37, Refs #203.
 *
 * Getestete Contracts:
 *   (1, 2 und 7 entfielen mit der Modellwahl-API, #903.)
 *   3. loadModels() Erfolg: setzt ollamaModels, ollamaReachable=true, loadingModels=false.
 *   4. loadModels() Fehler: setzt ollamaReachable=false, loadingModels=false, ruft onError auf.
 *   5. localStorage-Persistence Sprache: beim Mount geladen, Änderung schreibt zurück.
 *   6. Keine Modellwahl mehr: Legacy-Keys unberührt, keine Modellwahl-API (#890/#903).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { useEnvForm, STORAGE_LANG } from '../useEnvForm'

// Issue #890: STORAGE_MODEL/STORAGE_CUSTOM_MODEL sind aus useEnvForm.ts
// entfernt worden — die Keys existieren nicht mehr im Produktionscode.
// Diese Tests beweisen genau das (Produktion ignoriert diese Keys), duerfen
// also nicht von einem Export dieser Keys abhaengen. Lokale Testkonstanten:
const STORAGE_MODEL = 'agora.lastModel'
const STORAGE_CUSTOM_MODEL = 'agora.lastCustomModel'

// ---------------------------------------------------------------------------
// Mock t() — identity function; tests check key suffixes, not translated text
// ---------------------------------------------------------------------------

const t = (key: string, params?: Record<string, unknown>): string =>
  params ? `${key}(${Object.values(params).join(',')})` : key

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
          default_provider: 'ollama',
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
      expect(f.defaultProvider.value).toBe('ollama')
      expect(f.serverDefaultRequiresOllama.value).toBe(true)
      expect(f.ollamaReachable.value).toBe(true)
      expect(f.agentToolsEnabled.value).toBe(false)
      expect(f.maxToolCallsPerAction.value).toBe(3)
      expect(f.loadingModels.value).toBe(false)
    })

    it('setzt bei OpenAI-Default kein lokales Ollama als Pflicht voraus', async () => {
      mockedGetAvailableModels.mockResolvedValue({
        success: true,
        data: {
          ollama: [],
          presets: [],
          current_default: 'gpt-5.4-mini',
          default_provider: 'openai',
          ollama_reachable: false,
          agent_tools_enabled: false,
          max_tool_calls_per_action: 2,
        },
      } as never)

      const f = useEnvForm({ t })
      await f.loadModels()

      expect(f.defaultProvider.value).toBe('openai')
      expect(f.serverDefaultRequiresOllama.value).toBe(false)
      expect(f.ollamaReachable.value).toBe(false)
    })

    it('setzt language aus default_language wenn STORAGE_LANG noch nicht gesetzt', async () => {
      mockedGetAvailableModels.mockResolvedValue({
        success: true,
        data: {
          ollama: [],
          presets: [],
          current_default: '',
          default_provider: 'unknown',
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
          default_provider: 'unknown',
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
  // Case 6 — Storage-Cut Modellauswahl (Issue #890)
  //
  // useEnvForm persistiert Modellauswahl NICHT mehr — agora.lastModel /
  // agora.lastCustomModel sind Legacy-Keys, die weder gelesen noch aktiv
  // geloescht werden. Die kanonische Senke ist jetzt Step2EnvSetup.selectedModelRef
  // (AiModelRef via AiModelPicker), nicht mehr modelOption/customModel.
  // -------------------------------------------------------------------------

  describe('Case 6 — Storage-Cut: Modellauswahl wird NICHT mehr persistiert (#890)', () => {
    it('liest und schreibt die Legacy-Modell-Keys nicht (und loescht Altwerte nicht aktiv)', async () => {
      localStorageStub.setItem(STORAGE_MODEL, 'irgendein-modell')

      const f = useEnvForm({ t })
      f.language.value = 'en'
      await nextTick()
      await nextTick()

      expect(localStorageStub.getItem(STORAGE_MODEL)).toBe('irgendein-modell')
      expect(localStorageStub.getItem(STORAGE_CUSTOM_MODEL)).toBeNull()
    })

    it('#903: exponiert keine Modellwahl-API mehr — Modellwahl laeuft ausschliesslich ueber AiModelRef', () => {
      const f = useEnvForm({ t }) as unknown as Record<string, unknown>
      for (const dead of ['modelOption', 'customModel', 'modelOptions', 'effectiveModel']) {
        expect(f).not.toHaveProperty(dead)
      }
    })
  })
})
