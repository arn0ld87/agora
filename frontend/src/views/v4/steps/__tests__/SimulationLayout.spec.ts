/**
 * SimulationLayout — Fix #1713.
 *
 * Deckt ab, was vorher (teilweise) in StepWrapperViews.spec.ts und
 * runParamsHandover.spec.ts fuer StepSimulationView lag, bevor Kopf,
 * Breadcrumbs, Stepper und Tabs hierher gewandert sind:
 * 1. AppShell/PipelineStepper/Breadcrumbs werden mit simulationId gerendert.
 * 2. SimTabsBar bekommt den korrekten activeTab je Route (inkl. Namens-Prefix
 *    fuer SimThreadFocus, Slice UI-2b #1713).
 * 3. Fehlt projectId in der Query, laedt das Layout es einmalig ueber
 *    getSimulation() nach, statt den Rueckweg still abzubrechen.
 * 4. clearSimFeed/clearSimClock laufen beim Unmount des Layouts (Verlassen
 *    der gesamten Simulation), nicht bei jedem Tab-Wechsel.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const routerPush = vi.hoisted(() => vi.fn())
const routerReplace = vi.hoisted(() => vi.fn())
const routerResolve = vi.hoisted(() => vi.fn(() => ({ path: '/v4/simulation/sim_x' })))
const route = vi.hoisted(() => ({
  name: 'StepSimulation',
  params: { simulationId: 'sim_x' },
  query: { projectId: 'project_42' } as Record<string, unknown>,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush, replace: routerReplace, resolve: routerResolve }),
  useRoute: () => route,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const getSimulationMock = vi.hoisted(() => vi.fn())
vi.mock('@/api/simulation', () => ({
  getSimulation: getSimulationMock,
}))

const clearSimFeedMock = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useSimFeed', () => ({
  clearSimFeed: clearSimFeedMock,
}))

const clearSimClockMock = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useSimClock', () => ({
  clearSimClock: clearSimClockMock,
}))

import SimulationLayout from '../SimulationLayout.vue'
import { useShellStore } from '@/stores/shell'

const STUBS = {
  PageHeader: { name: 'PageHeader', props: ['title', 'subtitle'], template: '<header><slot name="right" /></header>' },
  PipelineStepper: { name: 'PipelineStepper', props: ['currentStep'], template: '<div />' },
  StepModelOverrideChip: true,
  SimTabsBar: {
    name: 'SimTabsBar',
    props: ['activeTab', 'simulationId'],
    template: '<nav />',
  },
  RouterView: { template: '<div />' },
}

function mountLayout() {
  return mount(SimulationLayout, {
    props: { simulationId: 'sim_x' },
    global: { stubs: STUBS },
  })
}

describe('SimulationLayout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routerPush.mockClear()
    routerReplace.mockClear()
    getSimulationMock.mockReset()
    clearSimFeedMock.mockClear()
    clearSimClockMock.mockClear()
    route.name = 'StepSimulation'
    route.query = { projectId: 'project_42' }
  })

  it('rendert PipelineStepper mit currentStep=3 und Breadcrumbs mit der simulationId', () => {
    const w = mountLayout()
    const stepper = w.getComponent({ name: 'PipelineStepper' })
    expect(stepper.props('currentStep')).toBe(3)
    const breadcrumbs = useShellStore().breadcrumbs
    expect(breadcrumbs.some((c) => c.label === 'sim_x')).toBe(true)
  })

  it.each([
    ['StepSimulation', 'pipeline'],
    ['StepSimulationFeed', 'feed'],
    ['SimThreads', 'threads'],
    ['SimThreadFocus', 'threads'],
    ['SimRounds', 'rounds'],
    ['SimActions', 'actions'],
  ])('reicht activeTab=%s → %s an SimTabsBar durch', (routeName, expectedTab) => {
    route.name = routeName
    const w = mountLayout()
    const tabsBar = w.getComponent({ name: 'SimTabsBar' })
    expect(tabsBar.props('activeTab')).toBe(expectedTab)
    expect(tabsBar.props('simulationId')).toBe('sim_x')
  })

  it('laedt projectId nach, wenn es in der Query fehlt', async () => {
    route.query = {}
    getSimulationMock.mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_x', project_id: 'project_from_api', status: 'running' },
    })

    mountLayout()
    await flushPromises()

    expect(getSimulationMock).toHaveBeenCalledWith('sim_x')
    expect(routerReplace).toHaveBeenCalledWith({ query: { projectId: 'project_from_api' } })
  })

  it('laedt nicht nach, wenn projectId bereits in der Query steht', async () => {
    mountLayout()
    await flushPromises()

    expect(getSimulationMock).not.toHaveBeenCalled()
  })

  it('raeumt Feed/Clock erst beim Verlassen der gesamten Simulation auf (Unmount)', () => {
    const w = mountLayout()
    expect(clearSimFeedMock).not.toHaveBeenCalled()
    expect(clearSimClockMock).not.toHaveBeenCalled()

    w.unmount()

    expect(clearSimFeedMock).toHaveBeenCalledWith('sim_x')
    expect(clearSimClockMock).toHaveBeenCalledWith('sim_x')
  })
})
