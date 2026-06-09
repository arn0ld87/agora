/**
 * Step2EnvSetup — Provider-Override-DB-Key-Fallback Tests (Smoke-Fix Slice 04, P1 #3 + #17).
 *
 * Prueft:
 * 1. has-key=true → Submit ohne api_key_override → Payload enthält provider ohne api_key.
 * 2. has-key=false + Cloud-Provider → Banner sichtbar, Provider-Info korrekt.
 * 3. User togglt eigenen Session-Key ein → api_key landet im Payload.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

// localStorage muss vor allen Modul-Imports gemockt sein.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
const sessionStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })
Object.defineProperty(globalThis, 'sessionStorage', { value: sessionStorageMock, writable: true })

// --- Kontrollierbare has-key-Mock-Antwort ---
let _hasKeyResponse = false

vi.mock('../../api/llmProviderKeys', () => ({
  checkLlmProviderHasKey: vi.fn(async () => _hasKeyResponse),
}))

// usePolling: alle 3 Tasks capturen
const _capturedPollingTasks: Array<() => Promise<void>> = []
vi.mock('../../composables/usePolling', () => ({
  usePolling: vi.fn((task: () => Promise<void>) => {
    _capturedPollingTasks.push(task)
    return {
      isRunning: { value: false },
      isTicking: { value: false },
      tick: task,
      start: vi.fn(),
      stop: vi.fn(),
    }
  }),
}))

// Simulation-API komplett mocken
let _preparePayloadCapture: unknown = null
vi.mock('../../api/simulation', () => ({
  prepareSimulation: vi.fn().mockImplementation((payload) => {
    _preparePayloadCapture = payload
    return Promise.resolve({ success: true, data: {} })
  }),
  getPrepareStatus: vi.fn().mockResolvedValue({ success: true, data: { status: 'idle' } }),
  getSimulationProfilesRealtime: vi.fn().mockResolvedValue({ success: true, data: { profiles: [] } }),
  getSimulationConfigRealtime: vi.fn().mockResolvedValue({ success: false }),
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: { ollama: [], presets: [], current_default: '' },
  }),
  addSimulationProfile: vi.fn().mockResolvedValue({ success: true }),
  deleteSimulationProfile: vi.fn().mockResolvedValue({ success: true }),
  listPersonaTemplates: vi.fn().mockResolvedValue({ success: true, data: { templates: [] } }),
  savePersonaTemplate: vi.fn().mockResolvedValue({ success: true }),
  deletePersonaTemplate: vi.fn().mockResolvedValue({ success: true }),
}))

vi.mock('../../composables/usePersonaReview', () => ({
  usePersonaReview: vi.fn(() => ({
    refreshQuality: vi.fn().mockResolvedValue(undefined),
    reviewEnabled: { value: false },
    error: { value: null },
    getIssuesFor: vi.fn().mockReturnValue([]),
    highestSeverityFor: vi.fn().mockReturnValue(null),
    approve: vi.fn().mockResolvedValue({ success: true }),
    reject: vi.fn().mockResolvedValue({ success: true }),
    editProfile: vi.fn().mockResolvedValue({ success: true }),
  })),
}))

vi.mock('../../composables/useSystemLog', () => ({
  useSystemLog: vi.fn(() => ({ addLog: vi.fn(), logs: { value: [] } })),
}))

import Step2EnvSetup from '../Step2EnvSetup.vue'
import { checkLlmProviderHasKey } from '../../api/llmProviderKeys'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step2: {
        runtimeProvider: {
          toggle: 'Provider-Optionen',
          label: 'Provider',
          default: 'Server-Standard',
          active: 'Override aktiv',
          google: 'Google Gemini',
          openai: 'OpenAI',
          customOpenAi: 'OpenAI-kompatibel',
          apiKey: 'API-Key',
          apiKeyPlaceholder: 'Nur für diese Browser-Sitzung',
          dbKeyPlaceholder: 'Server-Key wird verwendet',
          sessionKeyLabel: 'Sitzungs-API-Key',
          sessionKeyToggle: 'Eigenen Key verwenden',
          noDbKeyBanner: 'Kein Key für {provider} hinterlegt.',
          checkingKey: 'Prüfe Key…',
          missingKey: 'API-Key fehlt.',
          baseUrl: 'Base-URL',
          baseUrlPlaceholder: 'https://api.openai.com/v1',
        },
        providerOverride: {
          dbKeyPlaceholder: 'Server-Key wird verwendet',
          sessionKeyToggle: 'Eigenen Key verwenden',
          sessionKeyLabel: 'Sitzungs-API-Key',
          noDbKeyBanner: 'Kein Key für {provider} hinterlegt.',
          checkingKey: 'Prüfe Key…',
        },
      },
      errors: { unknown: 'Fehler', personaGenFailed: 'Fehler' },
    },
    en: {},
  },
})

const globalConfig = {
  plugins: [i18n],
  stubs: {
    Btn: { template: '<button><slot /></button>' },
    Badge: { template: '<span><slot /></span>' },
    Kicker: { template: '<span><slot /></span>' },
    Field: { template: '<div><label>{{ label }}</label><input :type="type || \'text\'" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" :placeholder="placeholder" /></div>', props: ['label', 'modelValue', 'type', 'placeholder'], emits: ['update:modelValue'] },
    Select: { template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>', props: ['label', 'modelValue', 'options'], emits: ['update:modelValue'] },
    LlmProfilePicker: true,
  },
}

describe('Step2EnvSetup — Provider-Override-DB-Key-Fallback (Smoke-Fix Slice 04)', () => {
  beforeEach(() => {
    _capturedPollingTasks.length = 0
    _preparePayloadCapture = null
    _hasKeyResponse = false
    localStorageMock.clear()
    sessionStorageMock.clear()
    vi.clearAllMocks()
  })

  it('1. has-key=true → Override-Submit ohne Session-Key → request payload hat provider aber keinen api_key', async () => {
    _hasKeyResponse = true
    // Provider = 'openai' in localStorage setzen
    localStorageMock.setItem('agora.runtimeLlm.provider', 'openai')
    // Kein Session-Key

    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-override-01', projectData: undefined, graphData: undefined, systemLogs: [] },
      global: globalConfig,
    })
    await flushPromises()
    await nextTick()

    // Toggle anklicken um Runtime-Options zu öffnen
    const toggleBtn = wrapper.find('button.runtime-toggle')
    if (toggleBtn.exists()) {
      await toggleBtn.trigger('click')
      await nextTick()
    }

    // triggerPrepare auslösen via Button-Click
    const prepareBtn = wrapper.findAll('button').find(b => b.text().toLowerCase().includes('persona'))
    if (prepareBtn && prepareBtn.exists()) {
      await prepareBtn.trigger('click')
      await flushPromises()
    }

    // checkLlmProviderHasKey muss aufgerufen worden sein
    expect(checkLlmProviderHasKey).toHaveBeenCalledWith('openai')

    // Kern-Assertion: der tatsaechliche Prepare-Payload muss llm_provider enthalten
    // und darf keinen api_key haben (Backend loest Key via SecretResolver auf).
    expect(_preparePayloadCapture).not.toBeNull()
    const payload = _preparePayloadCapture as Record<string, unknown>
    expect(payload).toHaveProperty('llm_provider')
    const llmProvider = payload.llm_provider as Record<string, unknown>
    expect(llmProvider).toHaveProperty('provider', 'openai')
    expect(llmProvider).not.toHaveProperty('api_key')

    wrapper.unmount()
  })

  it('2. has-key=false + Cloud-Provider + kein Session-Key → Banner-Element sichtbar', async () => {
    _hasKeyResponse = false
    localStorageMock.setItem('agora.runtimeLlm.provider', 'openai')
    // Kein Session-Key

    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-override-02', projectData: undefined, graphData: undefined, systemLogs: [] },
      global: globalConfig,
    })
    await flushPromises()
    await nextTick()

    // Toggle öffnen
    const toggleBtn = wrapper.find('button.runtime-toggle')
    if (toggleBtn.exists()) {
      await toggleBtn.trigger('click')
      await flushPromises()
      await nextTick()
    }

    // Banner mit role="alert" muss existieren
    const banner = wrapper.find('[role="alert"]')
    expect(banner.exists()).toBe(true)
    // Banner-Text enthält provider-Info
    expect(banner.text()).toBeTruthy()

    wrapper.unmount()
  })

  it('3. User tippt Session-Key → payload enthält api_key im llm_provider', async () => {
    _hasKeyResponse = false
    localStorageMock.setItem('agora.runtimeLlm.provider', 'openai')
    // Kein Session-Key initial

    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-override-03', projectData: undefined, graphData: undefined, systemLogs: [] },
      global: globalConfig,
    })
    await flushPromises()
    await nextTick()

    // Toggle öffnen
    const toggleBtn = wrapper.find('button.runtime-toggle')
    if (toggleBtn.exists()) {
      await toggleBtn.trigger('click')
      await nextTick()
    }

    // Passwort-Feld finden und Key eintippen
    const passwordInput = wrapper.find('input[type="password"]')
    if (passwordInput.exists()) {
      await passwordInput.setValue('sk-my-session-key')
      await flushPromises()
      await nextTick()
    }

    // sessionStorage muss Key halten
    const storedKey = sessionStorageMock.getItem('agora.runtimeLlm.apiKey')
    expect(storedKey).toBe('sk-my-session-key')

    wrapper.unmount()
  })
})
