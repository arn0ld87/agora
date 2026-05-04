// Issue #220 (Slice J.2) — SimulationRunView-Akzeptanztests.
//
// Belegt:
//  1. Nach Mount werden KEINE /run-status-Requests gefeuert
//     (statusPolling vollständig entfernt).
//  2. Ein update-progress-Event von Step3Simulation propagiert
//     paused/current_round/total_rounds korrekt in statusText.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

// ── vue-i18n minimal stubben ────────────────────────────────────────────────
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key, vars) =>
      vars ? `${key}:${JSON.stringify(vars)}` : key,
  }),
}))

// ── api/simulation stubben — getRunStatus darf niemals aufgerufen werden ────
vi.mock('../../api/simulation', () => ({
  getSimulation: vi.fn().mockResolvedValue({ success: false }),
  getSimulationConfig: vi.fn().mockResolvedValue({ success: false }),
  stopSimulation: vi.fn().mockResolvedValue({ success: true }),
  closeSimulationEnv: vi.fn().mockResolvedValue({ success: true }),
  getEnvStatus: vi.fn().mockResolvedValue({ success: true, data: { env_alive: false } }),
  getRunStatus: vi.fn().mockResolvedValue({ success: false }),
  pauseSimulation: vi.fn().mockResolvedValue({ success: true }),
  resumeSimulation: vi.fn().mockResolvedValue({ success: true }),
}))

// ── api/graph stubben ────────────────────────────────────────────────────────
vi.mock('../../api/graph', () => ({
  getProject: vi.fn().mockResolvedValue({ success: false }),
  getGraphData: vi.fn().mockResolvedValue({ success: false }),
}))

// ── Composables stubben ──────────────────────────────────────────────────────
vi.mock('../../composables/useSystemLog', () => ({
  useSystemLog: () => ({
    systemLogs: [],
    addLog: vi.fn(),
  }),
}))

vi.mock('../../composables/useWorkspaceMode', () => ({
  useWorkspaceMode: () => ({
    viewMode: 'split',
    workspaceModes: [],
    leftPanelStyle: {},
    rightPanelStyle: {},
    toggleMaximize: vi.fn(),
  }),
}))

vi.mock('../../composables/usePolling', () => ({
  usePolling: (_fn, _ms) => ({
    start: vi.fn(),
    stop: vi.fn(),
  }),
}))

// ── Kind-Komponenten komplett stubben ────────────────────────────────────────
const Step3SimulationStub = {
  name: 'Step3Simulation',
  props: ['simulationId', 'maxRounds', 'simulationDays', 'minutesPerRound', 'projectData', 'graphData', 'systemLogs'],
  emits: ['go-back', 'next-step', 'add-log', 'update-status', 'update-progress'],
  template: '<div data-testid="step3-stub" />',
}

import { getRunStatus } from '../../api/simulation'
import SimulationRunView from '../SimulationRunView.vue'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulation/:simulationId/run',
        name: 'SimulationRun',
        component: SimulationRunView,
      },
      {
        path: '/simulation/:simulationId',
        name: 'Simulation',
        component: { template: '<div />' },
      },
    ],
  })
}

async function mountView(simulationId = 'sim-test-123') {
  const router = makeRouter()
  await router.push(`/simulation/${simulationId}/run`)
  await router.isReady()

  const wrapper = mount(SimulationRunView, {
    global: {
      plugins: [router],
      stubs: {
        Step3Simulation: Step3SimulationStub,
        GraphPanel: { template: '<div data-testid="graph-panel-stub" />' },
        WorkspaceLayout: { template: '<div><slot name="header" /><slot /></div>' },
        WorkspaceHeader: { template: '<div><slot name="brand" /><slot name="center" /><slot name="status" /></div>' },
        WorkspaceBrandLink: { template: '<span><slot /></span>' },
        WorkspaceModeSwitch: { template: '<div />' },
        WorkspaceSplit: { template: '<div><slot name="left" /><slot name="right" /></div>' },
        WorkspaceStepStatus: { template: '<div><slot /></div>' },
      },
    },
  })

  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.resetAllMocks()
  // Defaults nach Reset neu setzen
  getRunStatus.mockResolvedValue({ success: false })
})

afterEach(() => {
  vi.resetAllMocks()
})


describe('SimulationRunView (Slice J.2 / Issue #220)', () => {
  it('feuert nach Mount keine /run-status-Requests (statusPolling entfernt)', async () => {
    await mountView()

    // 50 ms warten — falls ein Poll noch feuern würde, wäre er hier sichtbar.
    await new Promise((r) => setTimeout(r, 50))

    expect(getRunStatus).not.toHaveBeenCalled()
  })

  it('propagiert update-progress-Event korrekt in statusText', async () => {
    const wrapper = await mountView()

    // Step3Simulation-Stub suchen und update-progress emittieren.
    const step3 = wrapper.findComponent({ name: 'Step3Simulation' })
    expect(step3.exists()).toBe(true)

    await step3.vm.$emit('update-progress', {
      paused: true,
      current_round: 5,
      total_rounds: 10,
    })
    await wrapper.vm.$nextTick()

    // statusText wird über computed() aus isPaused + currentRound + totalRounds gebaut.
    // Mit dem t-Stub ergibt sich:
    //   t('step3.status.paused', { current: 5, total: 10 })
    //   => 'step3.status.paused:{"current":5,"total":10}'
    const vm = wrapper.vm
    expect(vm.isPaused).toBe(true)
    expect(vm.currentRound).toBe(5)
    expect(vm.totalRounds).toBe(10)
    expect(vm.statusText).toContain('step3.status.paused')
    expect(vm.statusText).toContain('"current":5')
    expect(vm.statusText).toContain('"total":10')
  })
})
