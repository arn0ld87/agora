/**
 * Step2EnvSetup — refreshQuality-Tick-Isolation Tests (Sub-Slice J.1, Issue #219).
 *
 * Prueft: 5 Profile-Polls → genau 1 refreshQuality-Call (vorher: 5).
 * Der watch auf profiles.value.length darf refreshQuality nur beim
 * Übergang 0 → n>0 feuern, nicht bei jedem weiteren Tick.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

// localStorage muss vor allen Modul-Imports gemockt sein,
// da i18n/index.js bei Import-Zeit localStorage.getItem aufruft.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// Capture polling task functions as they are registered.
// usePolling is called 3× in order: pollPrepareStatus (0), fetchProfilesRealtime (1), fetchConfigRealtime (2).
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

// --- Mutable mock state so individual tests can control API responses ---
let _profilesResponse: unknown = { success: true, data: { profiles: [] } }

vi.mock('../../api/simulation', () => ({
  prepareSimulation: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getPrepareStatus: vi.fn().mockResolvedValue({ success: true, data: { status: 'idle' } }),
  getSimulationProfilesRealtime: vi.fn().mockImplementation(() =>
    Promise.resolve(_profilesResponse),
  ),
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

// refreshQuality-Spy.
const refreshQualitySpy = vi.fn().mockResolvedValue(undefined)

vi.mock('../../composables/usePersonaReview', () => ({
  usePersonaReview: vi.fn(() => ({
    refreshQuality: refreshQualitySpy,
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
import { getAvailableModels, prepareSimulation } from '../../api/simulation'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

// Minimaler AiModelPicker-Stub, gemeinsam genutzt in Test-Suites, die den
// Picker nicht selbst pruefen (vermeidet Pinia-Abhaengigkeit von
// useAvailableModels() beim Mount von Step2EnvSetup — Issue #890).
const passiveAiModelPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'disabled', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template: '<div data-testid="ai-model-picker-passive-stub" />',
}

const globalConfig = {
  plugins: [i18n],
  stubs: {
    Btn: { template: '<button><slot /></button>' },
    Badge: { template: '<span><slot /></span>' },
    Kicker: { template: '<span><slot /></span>' },
    Field: { template: '<div><slot /></div>' },
    Select: { template: '<select><slot /></select>' },
    AiModelPicker: passiveAiModelPickerStub,
  },
}

describe('Step2EnvSetup — refreshQuality-Tick-Isolation (J.1, #219)', () => {
  beforeEach(() => {
    refreshQualitySpy.mockClear()
    _capturedPollingTasks.length = 0
    _profilesResponse = { success: true, data: { profiles: [] } }
  })

  it('ruft refreshQuality bei 5 Polling-Ticks genau 1× auf (nur beim 0→n>0-Übergang)', async () => {
    mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-test-001',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    // usePolling ist 3× aufgerufen worden:
    // Index 0: pollPrepareStatus, Index 1: fetchProfilesRealtime, Index 2: fetchConfigRealtime
    expect(_capturedPollingTasks.length).toBeGreaterThanOrEqual(2)
    const fetchProfilesTask = _capturedPollingTasks[1]
    expect(typeof fetchProfilesTask).toBe('function')

    // Tick 1: profiles arrive (0 → 3) — watch should call refreshQuality 1×.
    _profilesResponse = {
      success: true,
      data: { profiles: [{ username: 'a' }, { username: 'b' }, { username: 'c' }] },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)

    // Ticks 2–5: same profiles count (3 → 3), no 0→n transition — no additional calls.
    for (let i = 0; i < 4; i++) {
      await fetchProfilesTask()
      await flushPromises()
      await nextTick()
    }

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)
    expect(refreshQualitySpy).toHaveBeenCalledWith('sim-test-001')
  })

  it('ruft refreshQuality bei Sim-Wechsel wieder 1× auf — neue Sim startet direkt mit Profilen (kein leerer Zwischen-Tick)', async () => {
    // Real scenario: sim-second already has profiles when simulationId prop changes.
    // The 1-watch variant must detect simId change (not profile 0→n transition)
    // and fire refreshQuality(simIdB) exactly once.
    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-first',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    const fetchProfilesTask = _capturedPollingTasks[1]
    expect(typeof fetchProfilesTask).toBe('function')

    // Sim A: 3 profiles arrive → refreshQuality for sim-first.
    _profilesResponse = {
      success: true,
      data: { profiles: [{ username: 'a' }, { username: 'b' }, { username: 'c' }] },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)
    expect(refreshQualitySpy).toHaveBeenNthCalledWith(1, 'sim-first')

    // Sim-Wechsel: simulationId changes, sim-second already returns 5 profiles immediately.
    // No empty-profiles intermediate tick — this is the realistic production path.
    _profilesResponse = {
      success: true,
      data: {
        profiles: [
          { username: 'u' }, { username: 'v' }, { username: 'w' },
          { username: 'x' }, { username: 'y' },
        ],
      },
    }
    await wrapper.setProps({ simulationId: 'sim-second' })
    await flushPromises()
    await nextTick()

    // First poll for sim-second (with profiles already present) must trigger refreshQuality.
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    // Total: 1× for sim-first + 1× for sim-second = 2.
    expect(refreshQualitySpy).toHaveBeenCalledTimes(2)
    expect(refreshQualitySpy).toHaveBeenNthCalledWith(2, 'sim-second')

    wrapper.unmount()
  })

  it('feuert refreshQuality NICHT erneut wenn Profile-Anzahl innerhalb derselben Sim wächst (Guard hält)', async () => {
    // Guard must suppress re-triggers when profiles grow (e.g. 3 → 5 → 7) within the same sim.
    mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-stable',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    const fetchProfilesTask = _capturedPollingTasks[1]
    expect(typeof fetchProfilesTask).toBe('function')

    // First poll: 3 profiles — must trigger refreshQuality once.
    _profilesResponse = {
      success: true,
      data: { profiles: [{ username: 'a' }, { username: 'b' }, { username: 'c' }] },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)

    // Subsequent polls: profile count grows (5, then 7) — guard must block re-triggers.
    _profilesResponse = {
      success: true,
      data: {
        profiles: [
          { username: 'a' }, { username: 'b' }, { username: 'c' },
          { username: 'd' }, { username: 'e' },
        ],
      },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    _profilesResponse = {
      success: true,
      data: {
        profiles: [
          { username: 'a' }, { username: 'b' }, { username: 'c' },
          { username: 'd' }, { username: 'e' }, { username: 'f' }, { username: 'g' },
        ],
      },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    // Still exactly 1 call — guard held.
    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)
    expect(refreshQualitySpy).toHaveBeenCalledWith('sim-stable')
  })

  it('setzt den Agenten-Cap-Slider auf den Persona-Pool-Floor 10 (smoke #6: 50→10)', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-floor',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    await nextTick()

    expect(wrapper.find('input[type="range"]').attributes('min')).toBe('10')
    expect(wrapper.find('input[type="number"]').attributes('min')).toBe('10')
    expect(wrapper.find('input[type="range"]').attributes('title')).toContain('minimumHint')

    wrapper.unmount()
  })
})

// Issue #834: EnvSetupModelPanel — v3-Profil-Legacy-Picker entfernt.
// Der Prepare-Payload-Vertrag (triggerPrepare liest weiterhin
// props.projectData.llm_profile_id) bleibt unverändert — das ist der
// Backend-live Profil-Pfad (simulation_prepare.py expandiert llm_profile_id
// zu llm_model="profile:<id>") und explizit OUT OF SCOPE für diesen Slice.
// Migriert wird nur die UI-Senke: kein AiModelPicker hier (siehe Issue-Body),
// der Legacy-Picker-Block + is-overridden-by-profile-Zustand entfallen ersatzlos.
const i18nHints = createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de, en },
})

const globalConfigHints = {
  plugins: [i18nHints],
  stubs: {
    Btn: { template: '<button><slot /></button>' },
    Badge: { template: '<span><slot /></span>' },
    Kicker: { template: '<span><slot /></span>' },
    Field: { template: '<div><slot /></div>' },
    Select: { template: '<select><slot /></select>' },
    AiModelPicker: passiveAiModelPickerStub,
  },
}

// ---------------------------------------------------------------------------
// Issue #890 — kanonische AiModelRef-Selektion (Step 2)
// ---------------------------------------------------------------------------

const aiPickerStubModelRef = {
  name: 'AiModelPicker',
  props: ['modelValue', 'disabled', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template:
    '<div data-testid="ai-model-picker-stub" :data-disabled="disabled">'
    + '<button data-testid="pick-explicit" @click="$emit(\'update:modelValue\', '
    + "{ provider_connection_id: 'conn-x', model_id: 'model-x', source: 'explicit' })\">pick</button>"
    + '<button data-testid="deselect-explicit" @click="$emit(\'update:modelValue\', null)">deselect</button>'
    + '</div>',
}

const selectStubModelRef = {
  name: 'SelectStub',
  props: ['modelValue', 'label', 'options'],
  emits: ['update:modelValue'],
  template: '<select :data-label="label"></select>',
}

const globalConfigModelRef = {
  plugins: [i18nHints],
  stubs: {
    Btn: { template: '<button><slot /></button>' },
    Badge: { template: '<span><slot /></span>' },
    Kicker: { template: '<span><slot /></span>' },
    Field: { template: '<div><slot /></div>' },
    Select: selectStubModelRef,
    AiModelPicker: aiPickerStubModelRef,
  },
}

describe('Step2EnvSetup — kanonische AiModelRef-Selektion (Issue #890)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    ;(getAvailableModels as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { ollama: [], presets: [], current_default: '' },
    })
    ;(prepareSimulation as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: {} })
  })

  async function triggerPrepare(wrapper: ReturnType<typeof mount>) {
    await (wrapper.vm as unknown as { triggerPrepare: () => Promise<void> }).triggerPrepare()
    await flushPromises()
  }

  function lastPayload(): Record<string, unknown> {
    return (prepareSimulation as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0] as Record<string, unknown>
  }

  it('kein Projektprofil + keine Auswahl -> Payload enthaelt weder ai_model_ref noch llm_model', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-890-01', projectData: undefined, graphData: undefined, systemLogs: [] },
      global: globalConfigModelRef,
    })
    await flushPromises()
    await triggerPrepare(wrapper)

    const payload = lastPayload()
    expect(payload).not.toHaveProperty('ai_model_ref')
    expect(payload).not.toHaveProperty('llm_model')
    wrapper.unmount()
  })

  it('Projektprofil gesetzt + keine explizite Auswahl -> KEIN ai_model_ref, llm_profile_id wie bisher', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-890-02', projectData: { llm_profile_id: 'prof-xyz' }, graphData: undefined, systemLogs: [] },
      global: globalConfigModelRef,
    })
    await flushPromises()
    await triggerPrepare(wrapper)

    const payload = lastPayload()
    expect(payload).not.toHaveProperty('ai_model_ref')
    expect(payload.llm_profile_id).toBe('prof-xyz')
    wrapper.unmount()
  })

  it('explizite Auswahl -> genau ein ai_model_ref, kein llm_model/llm_profile_id/llm_provider', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-890-03', projectData: undefined, graphData: undefined, systemLogs: [] },
      global: globalConfigModelRef,
    })
    await flushPromises()

    await wrapper.find('[data-testid="pick-explicit"]').trigger('click')
    await triggerPrepare(wrapper)

    const payload = lastPayload()
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn-x',
      model_id: 'model-x',
      source: 'explicit',
    })
    expect(payload).not.toHaveProperty('llm_model')
    expect(payload).not.toHaveProperty('llm_profile_id')
    expect(payload).not.toHaveProperty('llm_provider')
    wrapper.unmount()
  })

  it('explizite Auswahl schlaegt Projektprofil: nur ai_model_ref, kein llm_profile_id', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-890-04', projectData: { llm_profile_id: 'prof-xyz' }, graphData: undefined, systemLogs: [] },
      global: globalConfigModelRef,
    })
    await flushPromises()

    await wrapper.find('[data-testid="pick-explicit"]').trigger('click')
    await triggerPrepare(wrapper)

    const payload = lastPayload()
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn-x',
      model_id: 'model-x',
      source: 'explicit',
    })
    expect(payload).not.toHaveProperty('llm_profile_id')
    wrapper.unmount()
  })

  it('Deselektion: nach expliziter Auswahl wieder null -> Payload wieder ohne ai_model_ref, mit llm_profile_id wie im Ausgangszustand', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-890-05', projectData: { llm_profile_id: 'prof-xyz' }, graphData: undefined, systemLogs: [] },
      global: globalConfigModelRef,
    })
    await flushPromises()

    await wrapper.find('[data-testid="pick-explicit"]').trigger('click')
    await wrapper.find('[data-testid="deselect-explicit"]').trigger('click')
    await triggerPrepare(wrapper)

    const payload = lastPayload()
    expect(payload).not.toHaveProperty('ai_model_ref')
    expect(payload.llm_profile_id).toBe('prof-xyz')
    wrapper.unmount()
  })

  it('Runtime-Provider aktiv -> kein ai_model_ref, stattdessen llm_provider + llm_model wie bisher', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: { simulationId: 'sim-890-06', projectData: undefined, graphData: undefined, systemLogs: [] },
      global: globalConfigModelRef,
    })
    await flushPromises()

    // Runtime-Provider-Panel aufklappen, dann ueber die Select-Stub-Komponente
    // (die v-model:runtime-provider bedient) ein Nicht-Default emittieren.
    const toggle = wrapper.find('.runtime-toggle')
    expect(toggle.exists()).toBe(true)
    await toggle.trigger('click')
    await flushPromises()

    const runtimeSelectComponent = wrapper
      .findAllComponents(selectStubModelRef)
      .find((c) => c.props('label') === de.step2.runtimeProvider.label)
    expect(runtimeSelectComponent).toBeTruthy()
    await runtimeSelectComponent!.vm.$emit('update:modelValue', 'openai')
    await flushPromises()
    await triggerPrepare(wrapper)

    const payload = lastPayload()
    expect(payload).not.toHaveProperty('ai_model_ref')
    expect(payload.llm_provider).toBeTruthy()
    wrapper.unmount()
  })
})

describe('Step2EnvSetup — EnvSetupModelPanel ohne v3-Profil-Legacy-Picker (Issue #834)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    ;(getAvailableModels as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { ollama: [], presets: [], current_default: '' },
    })
    ;(prepareSimulation as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: {} })
  })

  it('triggerPrepare-Payload trägt llm_profile_id, wenn projectData.llm_profile_id gesetzt ist', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-profile-01',
        projectData: { llm_profile_id: 'prof-abc' },
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })
    await flushPromises()

    await (wrapper.vm as unknown as { triggerPrepare: () => Promise<void> }).triggerPrepare()
    await flushPromises()

    expect(prepareSimulation).toHaveBeenCalled()
    const payload = (prepareSimulation as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0] as Record<string, unknown>
    expect(payload.llm_profile_id).toBe('prof-abc')

    wrapper.unmount()
  })

  it('triggerPrepare-Payload trägt kein llm_profile_id, wenn projectData es nicht setzt', async () => {
    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-profile-02',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })
    await flushPromises()

    await (wrapper.vm as unknown as { triggerPrepare: () => Promise<void> }).triggerPrepare()
    await flushPromises()

    expect(prepareSimulation).toHaveBeenCalled()
    const payload = (prepareSimulation as ReturnType<typeof vi.fn>).mock.calls.at(-1)![0] as Record<string, unknown>
    expect(payload).not.toHaveProperty('llm_profile_id')

    wrapper.unmount()
  })

  it('zeigt "loadingModels"-Hint sofort nach dem Mount (bevor loadModels() aufgelöst ist)', () => {
    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-hint-loading',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })

    expect(wrapper.text()).toContain(de.step2.model.loadingModels)

    wrapper.unmount()
  })

  it('zeigt "noOllama"-Hint wenn Server-Default Ollama verlangt und Ollama nicht erreichbar ist', async () => {
    ;(getAvailableModels as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        ollama: [], presets: [], current_default: '',
        default_provider: 'ollama', ollama_reachable: false,
      },
    })

    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-hint-ollama',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })
    await flushPromises()

    expect(wrapper.text()).toContain(de.step2.model.noOllama)

    wrapper.unmount()
  })

  it('zeigt "openAiDefault"-Hint wenn Server-Default openai ist', async () => {
    ;(getAvailableModels as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        ollama: [], presets: [], current_default: '',
        default_provider: 'openai', ollama_reachable: false,
      },
    })

    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-hint-openai',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })
    await flushPromises()

    expect(wrapper.text()).toContain(de.step2.model.openAiDefault)

    wrapper.unmount()
  })

  it('regression: die Model-Hint-Kette ist unabhängig von projectData.llm_profile_id (kein Sonderzweig mehr)', async () => {
    // Der frühere "modelIgnored"-Sonderzweig (samt i18n-Key
    // step2.llmProfile.modelIgnored) ist mit Issue #834 vollständig entfernt —
    // die Model-Hints hängen nur noch von loadingModels/serverDefault/ollama ab.
    const withProfile = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-hint-with-profile',
        projectData: { llm_profile_id: 'prof-abc' },
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })
    await flushPromises()

    const withoutProfile = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-hint-without-profile',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfigHints,
    })
    await flushPromises()

    expect(withProfile.text()).toBe(withoutProfile.text())

    withProfile.unmount()
    withoutProfile.unmount()
  })
})
