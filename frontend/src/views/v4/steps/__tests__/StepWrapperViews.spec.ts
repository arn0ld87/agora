/**
 * Step Wrapper Views — Smoke-Tests (Slice H, Design-v4).
 *
 * Prueft pro Wrapper-View:
 * 1. Mountet ohne Crash.
 * 2. AppShell ist im DOM vorhanden.
 * 3. PipelineStepper mit korrektem currentStep ist vorhanden.
 * 4. Korrekte Breadcrumb-Daten werden aus dem Props abgeleitet.
 *
 * Alle Step*.vue-Komponenten werden als Stubs gemountet —
 * ihre Inhalte sind eigenstaendige Slice-H-Folge-Tests.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

// ── localStorage-Mock ─────────────────────────────────────────────────────────
const lsMock = (() => {
  const s: Record<string, string> = {}
  return {
    getItem: (k: string) => s[k] ?? null,
    setItem: (k: string, v: string) => { s[k] = v },
    removeItem: (k: string) => { delete s[k] },
    clear: () => { Object.keys(s).forEach((k) => { delete s[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: lsMock, writable: true })

// ── vue-i18n minimal stubben ──────────────────────────────────────────────────
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'de' },
  }),
  createI18n: () => ({ install: vi.fn() }),
}))

// ── api/* stubben (Step-Komponenten nutzen diverse APIs) ──────────────────────
vi.mock('@/api/graph', () => ({
  getProject: vi.fn().mockResolvedValue({ success: false }),
  getGraphData: vi.fn().mockResolvedValue({ success: false }),
  buildGraph: vi.fn().mockResolvedValue({ success: false }),
}))
vi.mock('@/api/simulation', () => ({
  getSimulation: vi.fn().mockResolvedValue({ success: false }),
  getSimulationConfig: vi.fn().mockResolvedValue({ success: false }),
  stopSimulation: vi.fn().mockResolvedValue({ success: true }),
  closeSimulationEnv: vi.fn().mockResolvedValue({ success: true }),
  getEnvStatus: vi.fn().mockResolvedValue({ success: true, data: { env_alive: false } }),
  getRunStatus: vi.fn().mockResolvedValue({ success: false }),
  pauseSimulation: vi.fn().mockResolvedValue({ success: true }),
  resumeSimulation: vi.fn().mockResolvedValue({ success: true }),
  prepareSimulation: vi.fn().mockResolvedValue({ success: false }),
}))
vi.mock('@/api/report', () => ({
  getReport: vi.fn().mockResolvedValue({ success: false }),
  generateReport: vi.fn().mockResolvedValue({ success: false }),
  streamReport: vi.fn().mockResolvedValue({ success: false }),
}))
vi.mock('@/api/settings', () => ({
  fetchSettings: vi.fn().mockResolvedValue({ success: false }),
  fetchSettingsSchema: vi.fn().mockResolvedValue({ success: false }),
  openSettingsStream: vi.fn().mockResolvedValue({ close: vi.fn() }),
  putSettings: vi.fn().mockResolvedValue({ success: false }),
  putSecrets: vi.fn().mockResolvedValue({ success: false }),
}))

// ── Composables stubben ───────────────────────────────────────────────────────
vi.mock('@/composables/useSystemLog', () => ({
  useSystemLog: () => ({ systemLogs: [], addLog: vi.fn() }),
}))
vi.mock('@/composables/usePolling', () => ({
  usePolling: () => ({ start: vi.fn().mockResolvedValue(undefined), stop: vi.fn(), tick: vi.fn(), isRunning: { value: false } }),
}))
vi.mock('@/composables/useRunsPolling', () => ({
  useRunsPolling: () => ({
    runs: { value: [] },
    loading: { value: false },
    error: { value: '' },
    isRunning: { value: false },
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn(),
    refresh: vi.fn(),
  }),
}))
vi.mock('@/composables/usePersonaActions', () => ({
  usePersonaActions: () => ({
    regeneratePersona: vi.fn(),
    deletePersona: vi.fn(),
    approvePersona: vi.fn(),
  }),
}))
vi.mock('@/composables/usePersonaFilter', () => ({
  usePersonaFilter: () => ({
    filteredPersonas: { value: [] },
    filterQuery: { value: '' },
    selectedGroups: { value: [] },
    availableGroups: { value: [] },
  }),
}))
vi.mock('@/composables/usePersonaLibrary', () => ({
  usePersonaLibrary: () => ({
    libraryOpen: { value: false },
    libraryPersonas: { value: [] },
    openLibrary: vi.fn(),
    closeLibrary: vi.fn(),
    addFromLibrary: vi.fn(),
  }),
}))
vi.mock('@/composables/useSimulationPrepare', () => ({
  useSimulationPrepare: () => ({
    preparing: { value: false },
    prepareError: { value: null },
    prepare: vi.fn(),
  }),
}))
vi.mock('@/composables/usePersonaQuota', () => ({
  usePersonaQuota: () => ({
    quotaPlan: { value: null },
    quotaError: { value: null },
    fetchQuota: vi.fn(),
    saveQuota: vi.fn(),
  }),
}))
vi.mock('@/composables/useEnvForm', () => ({
  useEnvForm: () => ({
    form: { value: {} },
    errors: { value: {} },
    submit: vi.fn(),
  }),
}))

// ── Store-Mocks ───────────────────────────────────────────────────────────────
vi.mock('@/store/settings', () => ({
  useSettingsStore: () => ({
    settings: {},
    schema: null,
    fetch: vi.fn(),
    fetchSchema: vi.fn(),
  }),
}))

vi.mock('@/store/aiModels', () => ({
  useLlmProvidersStore: () => ({
    providers: [],
    entries: {},
    models: {},
    busy: {},
    hasKey: vi.fn().mockReturnValue(false),
    loadProviders: vi.fn().mockResolvedValue(undefined),
    saveKey: vi.fn().mockResolvedValue(undefined),
    revokeKey: vi.fn().mockResolvedValue(undefined),
    testProvider: vi.fn().mockResolvedValue({ connectivity: 'ok', models_found: 0 }),
    fetchModels: vi.fn().mockResolvedValue([]),
  }),
  useLlmRoutingDefaultsStore: () => ({
    defaults: { updated_at: null, global_default: null, stage_overrides: {} },
    globalDefault: null,
    stageOverrides: {},
    effectiveRouteForStage: vi.fn().mockReturnValue({ provider_id: '', model: '' }),
    load: vi.fn().mockResolvedValue(undefined),
    setGlobalDefault: vi.fn().mockResolvedValue(undefined),
    setStageOverride: vi.fn().mockResolvedValue(undefined),
    clearStageOverride: vi.fn().mockResolvedValue(undefined),
  }),
}))

// ── Router-Stub ───────────────────────────────────────────────────────────────
const stubComp = { template: '<div />' }
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'Home', component: stubComp },
    { path: '/runs', name: 'Runs', component: stubComp },
    { path: '/settings', name: 'Settings', component: stubComp },
    { path: '/v4/graph-build/:projectId', name: 'StepGraphBuild', component: stubComp },
    { path: '/v4/env-setup/:projectId', name: 'StepEnvSetup', component: stubComp },
    { path: '/v4/simulation/:simulationId', name: 'StepSimulation', component: stubComp },
    { path: '/v4/report/:reportId', name: 'StepReport', component: stubComp },
    { path: '/v4/interaction/:reportId', name: 'StepInteraction', component: stubComp },
  ],
})

// ── Shared mount-Helfer ───────────────────────────────────────────────────────
async function mountView<T extends object>(
  component: unknown,
  props: T,
  route = '/',
) {
  await router.push(route)
  await router.isReady()
  return mount(component as Parameters<typeof mount>[0], {
    props,
    global: {
        mocks: { $t: (key: any) => key },
      plugins: [router, createPinia()],
      stubs: {
        // Step-Komponenten als Stubs — ihre Inhalte sind Folge-Slice
        Step1GraphBuild: { template: '<div class="stub-step1" />' },
        Step2EnvSetup: { template: '<div class="stub-step2" />' },
        Step3Simulation: { template: '<div class="stub-step3" />' },
        Step4Report: { template: '<div class="stub-step4" />' },
        Step5Interaction: { template: '<div class="stub-step5" />' },
        // Sidebar stub (Slice F, nicht angefasst)
        Sidebar: { template: '<nav class="stub-sidebar" />' },
        // Model-Override-Chip (Slice E) — eigene Spec; hier nur Shell getestet
        StepModelOverrideChip: { template: '<div class="stub-model-chip" />' },
      },
    },
  })
}

// ── Imports nach Mocks ────────────────────────────────────────────────────────
import StepGraphBuildView from '../StepGraphBuildView.vue'
import StepEnvSetupView from '../StepEnvSetupView.vue'
import StepSimulationView from '../StepSimulationView.vue'
import StepReportView from '../StepReportView.vue'
import StepInteractionView from '../StepInteractionView.vue'

// ── Tests ─────────────────────────────────────────────────────────────────────
describe('StepGraphBuildView', () => {
  beforeEach(() => { lsMock.clear(); setActivePinia(createPinia()) })

  it('mountet ohne Crash', async () => {
    const w = await mountView(StepGraphBuildView, { projectId: 'proj-42' }, '/v4/graph-build/proj-42')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(StepGraphBuildView, { projectId: 'proj-42' }, '/v4/graph-build/proj-42')
    expect(w.find('.app-shell').exists()).toBe(true)
  })

  it('rendert PipelineStepper mit currentStep=1', async () => {
    const w = await mountView(StepGraphBuildView, { projectId: 'proj-42' }, '/v4/graph-build/proj-42')
    const stepper = w.findComponent({ name: 'PipelineStepper' })
    expect(stepper.exists()).toBe(true)
    expect(stepper.props('currentStep')).toBe(1)
  })

  it('Breadcrumb enthaelt projectId', async () => {
    const w = await mountView(StepGraphBuildView, { projectId: 'proj-42' }, '/v4/graph-build/proj-42')
    expect(w.text()).toContain('proj-42')
  })
})

describe('StepEnvSetupView', () => {
  beforeEach(() => { lsMock.clear(); setActivePinia(createPinia()) })

  it('mountet ohne Crash', async () => {
    const w = await mountView(StepEnvSetupView, { projectId: 'proj-42' }, '/v4/env-setup/proj-42')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(StepEnvSetupView, { projectId: 'proj-42' }, '/v4/env-setup/proj-42')
    expect(w.find('.app-shell').exists()).toBe(true)
  })

  it('rendert PipelineStepper mit currentStep=2', async () => {
    const w = await mountView(StepEnvSetupView, { projectId: 'proj-42' }, '/v4/env-setup/proj-42')
    const stepper = w.findComponent({ name: 'PipelineStepper' })
    expect(stepper.props('currentStep')).toBe(2)
  })
})

describe('StepSimulationView', () => {
  beforeEach(() => { lsMock.clear(); setActivePinia(createPinia()) })

  it('mountet ohne Crash', async () => {
    const w = await mountView(StepSimulationView, { simulationId: 'sim-99' }, '/v4/simulation/sim-99')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(StepSimulationView, { simulationId: 'sim-99' }, '/v4/simulation/sim-99')
    expect(w.find('.app-shell').exists()).toBe(true)
  })

  it('rendert PipelineStepper mit currentStep=3', async () => {
    const w = await mountView(StepSimulationView, { simulationId: 'sim-99' }, '/v4/simulation/sim-99')
    const stepper = w.findComponent({ name: 'PipelineStepper' })
    expect(stepper.props('currentStep')).toBe(3)
  })

  it('Breadcrumb enthaelt simulationId', async () => {
    const w = await mountView(StepSimulationView, { simulationId: 'sim-99' }, '/v4/simulation/sim-99')
    expect(w.text()).toContain('sim-99')
  })
})

describe('StepReportView', () => {
  beforeEach(() => { lsMock.clear(); setActivePinia(createPinia()) })

  it('mountet ohne Crash', async () => {
    const w = await mountView(StepReportView, { reportId: 'rpt-7' }, '/v4/report/rpt-7')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(StepReportView, { reportId: 'rpt-7' }, '/v4/report/rpt-7')
    expect(w.find('.app-shell').exists()).toBe(true)
  })

  it('rendert PipelineStepper mit currentStep=4', async () => {
    const w = await mountView(StepReportView, { reportId: 'rpt-7' }, '/v4/report/rpt-7')
    const stepper = w.findComponent({ name: 'PipelineStepper' })
    expect(stepper.props('currentStep')).toBe(4)
  })
})

describe('StepInteractionView', () => {
  beforeEach(() => { lsMock.clear(); setActivePinia(createPinia()) })

  it('mountet ohne Crash', async () => {
    const w = await mountView(StepInteractionView, { reportId: 'rpt-7' }, '/v4/interaction/rpt-7')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(StepInteractionView, { reportId: 'rpt-7' }, '/v4/interaction/rpt-7')
    expect(w.find('.app-shell').exists()).toBe(true)
  })

  it('rendert PipelineStepper mit currentStep=5', async () => {
    const w = await mountView(StepInteractionView, { reportId: 'rpt-7' }, '/v4/interaction/rpt-7')
    const stepper = w.findComponent({ name: 'PipelineStepper' })
    expect(stepper.props('currentStep')).toBe(5)
  })

  it('Breadcrumb enthaelt reportId', async () => {
    const w = await mountView(StepInteractionView, { reportId: 'rpt-7' }, '/v4/interaction/rpt-7')
    expect(w.text()).toContain('rpt-7')
  })

  // Regression: Die Route kennt nur die reportId. Ohne Durchreichen der
  // simulation_id laufen Chat, Interview und Profil-Liste in Step 5 ins Leere
  // (POST /api/simulation/undefined/chat -> 404).
  it('reicht ?runId aus der Query als simulationId an Step5Interaction durch', async () => {
    const w = await mountView(
      StepInteractionView,
      { reportId: 'rpt-7' },
      '/v4/interaction/rpt-7?runId=sim_28a4367b2937',
    )
    expect(w.find('.stub-step5').attributes('simulation-id')).toBe('sim_28a4367b2937')
  })

  it('setzt simulationId nicht, wenn ?runId fehlt (Komponente faellt auf Report zurueck)', async () => {
    const w = await mountView(StepInteractionView, { reportId: 'rpt-7' }, '/v4/interaction/rpt-7')
    expect(w.find('.stub-step5').attributes('simulation-id')).toBeUndefined()
  })
})
