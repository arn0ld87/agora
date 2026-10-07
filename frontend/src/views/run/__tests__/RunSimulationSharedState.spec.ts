import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import RunSimulationView from '../simulation/RunSimulationView.vue'
import de from '@/i18n/locales/de.json'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'
import type { SimulationRunState } from '@/composables/run/simulation/useSimulationRunState'
import { makeConsumer } from './sharedStateConsumer'

const h_ = vi.hoisted(() => ({
  streamStart: vi.fn(),
  streamCreated: vi.fn(),
  pollStart: vi.fn(),
  pollCreated: vi.fn(),
  getRunStatus: vi.fn(),
  getRunStatusDetail: vi.fn(),
  getRun: vi.fn(),
  seen: [] as unknown[],
}))

vi.mock('@/api/simulation', () => ({ getRunStatus: h_.getRunStatus, getRunStatusDetail: h_.getRunStatusDetail }))
vi.mock('@/api/runs', () => ({ getRun: h_.getRun }))
vi.mock('@/composables/useEventStream', () => ({
  useEventStream: () => {
    h_.streamCreated()
    return { start: h_.streamStart, stop: vi.fn() }
  },
}))
vi.mock('@/composables/usePolling', () => ({
  usePolling: () => {
    h_.pollCreated()
    return { start: h_.pollStart, stop: vi.fn() }
  },
}))

const seen = h_.seen as SimulationRunState[]
// Kopf und Feed sind je eine echte Verbraucherkomponente der gemeinsamen Instanz.
vi.mock('@/components/run/simulation/RunSimHeader.vue', async () => {
  const { makeConsumer } = await import('./sharedStateConsumer')
  return { default: makeConsumer(h_.seen as SimulationRunState[]) }
})
const Consumer = makeConsumer(seen)

const workspace = {
  state: ref('ready'),
  error: ref(null),
  data: ref({ jobs: { simulation_run: { runId: 'run_1', route: { model: 'm', providerId: 'p' } } } }),
  stages: ref([{ key: 'personas', state: 'done' }]),
  reload: vi.fn(),
}

async function mountShell() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId/simulation',
        name: 'RunSimulation',
        component: RunSimulationView,
        props: true,
        children: [
          { path: 'feed/:network(twitter|reddit)?', name: 'RunSimulationFeed', component: Consumer },
          { path: 'rounds', name: 'RunSimulationRounds', component: Consumer },
          { path: 'diagnostics', name: 'RunSimulationDiagnostics', component: Consumer },
          { path: 'post/:postId', name: 'RunSimulationPost', component: Consumer },
        ],
      },
    ],
  })
  await router.push('/simulations/sim_1/simulation/feed')
  await router.isReady()
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  const w = mount(defineComponent({ render: () => h(RouterView) }), {
    global: { plugins: [router, i18n], provide: { [RUN_WORKSPACE_KEY as symbol]: workspace } },
  })
  await flushPromises()
  return w
}

beforeEach(() => {
  seen.length = 0
  Object.values(h_).forEach((f) => typeof f === 'function' && f.mockReset())
  h_.streamStart.mockResolvedValue(undefined)
  h_.pollStart.mockResolvedValue(undefined)
  h_.getRunStatus.mockResolvedValue({ success: true, data: { runner_status: 'running', current_round: 1, total_rounds: 3 } })
  h_.getRun.mockResolvedValue({ success: true, data: { status: 'running' } })
})
afterEach(() => vi.clearAllMocks())

describe('RunSimulationView: gemeinsamer Laufstand', () => {
  it('Kopf und Feed teilen eine Instanz: genau ein Strom und ein Polling', async () => {
    const w = await mountShell()
    expect(w.findAll('[data-testid="consumer"]')).toHaveLength(2)
    expect(seen).toHaveLength(2)
    expect(seen[0]).toBe(seen[1])
    expect(h_.streamCreated).toHaveBeenCalledTimes(1)
    expect(h_.pollCreated).toHaveBeenCalledTimes(1)
    expect(h_.streamStart).toHaveBeenCalledTimes(1)
    expect(h_.pollStart).toHaveBeenCalledTimes(1)
    expect(h_.getRunStatus).toHaveBeenCalledTimes(1)
  })

  it('ohne Hülle legt der Verbraucher eine eigene Instanz an', () => {
    const w = mount(Consumer)
    expect(seen).toHaveLength(1)
    expect(h_.streamCreated).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})
