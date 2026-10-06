import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

const h_ = vi.hoisted(() => ({
  handlers: {} as { state?: (m: unknown) => void; control?: (m: unknown) => void },
  streamStart: vi.fn(),
  streamStop: vi.fn(),
  getRunStatus: vi.fn(),
  getRunStatusDetail: vi.fn(),
  getRun: vi.fn(),
}))

vi.mock('@/api/simulation', () => ({
  getRunStatus: h_.getRunStatus,
  getRunStatusDetail: h_.getRunStatusDetail,
}))
vi.mock('@/api/runs', () => ({ getRun: h_.getRun }))
vi.mock('@/composables/useEventStream', () => ({
  useEventStream: (_id: unknown, handlers: typeof h_.handlers) => {
    h_.handlers = handlers
    return { start: h_.streamStart, stop: h_.streamStop }
  },
}))

import { useSimulationRunState, type SimulationRunState } from '../useSimulationRunState'

const ok = (data: unknown) => ({ success: true, data })

function mountState(id: Ref<string>, runId?: Ref<string | null>) {
  let api!: SimulationRunState
  const wrapper: VueWrapper = mount(
    defineComponent({
      setup() {
        api = useSimulationRunState(() => id.value, { runId: () => runId?.value ?? null })
        return () => h('div')
      },
    }),
  )
  return { api, wrapper }
}

beforeEach(() => {
  vi.useFakeTimers()
  Object.values(h_).forEach((v) => typeof v === 'function' && 'mockReset' in v && (v as ReturnType<typeof vi.fn>).mockReset())
  h_.streamStart.mockResolvedValue(undefined)
  h_.getRun.mockResolvedValue(ok({ status: 'completed', usage: { totals: { cost_micros: 1_500_000 } } }))
})
afterEach(() => {
  vi.useRealTimers()
})

describe('useSimulationRunState', () => {
  it('lädt einen beendeten Lauf einmal, ohne Stream und Polling, inklusive Kosten', async () => {
    h_.getRunStatus.mockResolvedValue(
      ok({ runner_status: 'completed', current_round: 24, total_rounds: 24, twitter_actions_count: 30, reddit_actions_count: 12 }),
    )
    const { api, wrapper } = mountState(ref('sim_1'), ref('run_1'))
    await flushPromises()

    expect(api.stateKind.value).toBe('done')
    expect(api.currentRound.value).toBe(24)
    expect(api.totalRounds.value).toBe(24)
    expect(api.totalActions.value).toBe(42)
    expect(api.costMicros.value).toBe(1_500_000)
    expect(h_.streamStart).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(h_.getRunStatusDetail).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('verfolgt einen laufenden Lauf per SSE und Polling und räumt beim Ende auf', async () => {
    h_.getRunStatus.mockResolvedValue(ok({ runner_status: 'running', current_round: 1, total_rounds: 10 }))
    h_.getRunStatusDetail.mockResolvedValue(ok({ runner_status: 'completed', current_round: 10, total_rounds: 10 }))
    const { api, wrapper } = mountState(ref('sim_1'), ref('run_1'))
    await flushPromises()

    expect(api.stateKind.value).toBe('running')
    expect(h_.streamStart).toHaveBeenCalledTimes(1)

    h_.handlers.state?.({ payload: { runner_status: 'running', current_round: 4, total_rounds: 10 } })
    expect(api.currentRound.value).toBe(4)
    h_.handlers.control?.({ payload: { paused: true } })
    expect(api.stateKind.value).toBe('paused')
    h_.handlers.control?.({ payload: { paused: false } })

    await vi.advanceTimersByTimeAsync(2500)
    await flushPromises()
    expect(h_.getRunStatusDetail).toHaveBeenCalledWith('sim_1')
    expect(api.stateKind.value).toBe('done')
    expect(h_.streamStop).toHaveBeenCalled()
    expect(api.costMicros.value).toBe(1_500_000)

    h_.getRunStatusDetail.mockClear()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(h_.getRunStatusDetail).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('zeigt Stopp mit Budgetgrund als Budgetabbruch und nie als fertig', async () => {
    h_.getRunStatus.mockResolvedValue(ok({ runner_status: 'stopped', current_round: 3, total_rounds: 10 }))
    h_.getRun.mockResolvedValue(
      ok({ status: 'stopped', termination_reason: 'budget_cost', error: null, usage: { totals: { cost_micros: 2_000_000 } } }),
    )
    const { api, wrapper } = mountState(ref('sim_1'), ref('run_1'))
    await flushPromises()
    expect(api.stateKind.value).toBe('budget')
    expect(api.terminationReason.value).toBe('budget_cost')
    wrapper.unmount()
  })

  it('unterscheidet failed/process_restart von einem Nutzerstopp', async () => {
    h_.getRunStatus.mockResolvedValue(ok({ runner_status: 'failed', current_round: 2, total_rounds: 10 }))
    h_.getRun.mockResolvedValue(ok({ status: 'failed', termination_reason: 'process_restart', usage: null }))
    const { api, wrapper } = mountState(ref('sim_1'), ref('run_1'))
    await flushPromises()
    expect(api.stateKind.value).toBe('failed')
    expect(api.terminationReason.value).toBe('process_restart')
    expect(api.costMicros.value).toBeNull()
    wrapper.unmount()
  })

  it('meldet Vertragsbruch und success=false sichtbar in error', async () => {
    h_.getRunStatus.mockResolvedValueOnce(ok({ runner_status: 'running', current_round: 'x' }))
    const { api, wrapper } = mountState(ref('sim_1'))
    await flushPromises()
    expect(api.error.value).toContain('Vertragsbruch')
    expect(api.stateKind.value).toBe('notStarted')

    h_.getRunStatus.mockResolvedValueOnce({ success: false, error: 'Simulation nicht gefunden' })
    await api.reload()
    expect(api.error.value).toBe('Simulation nicht gefunden')
    wrapper.unmount()
  })

  it('setzt beim Wechsel der Kennung zurück und lädt neu; Unmount stoppt den Stream', async () => {
    h_.getRunStatus.mockResolvedValueOnce(ok({ runner_status: 'running', current_round: 5, total_rounds: 10 }))
    const id = ref('sim_1')
    const { api, wrapper } = mountState(id)
    await flushPromises()
    expect(api.currentRound.value).toBe(5)

    h_.getRunStatus.mockResolvedValueOnce(ok({ runner_status: 'idle' }))
    id.value = 'sim_2'
    await flushPromises()
    expect(h_.getRunStatus).toHaveBeenLastCalledWith('sim_2')
    expect(api.stateKind.value).toBe('notStarted')
    expect(api.currentRound.value).toBeNull()
    expect(h_.streamStop).toHaveBeenCalled()

    h_.streamStop.mockClear()
    wrapper.unmount()
    expect(h_.streamStop).toHaveBeenCalled()
  })

  it('übernimmt die run_id aus der Startantwort und lädt Kosten nach', async () => {
    h_.getRunStatus.mockResolvedValue(ok({ runner_status: 'completed' }))
    const { api, wrapper } = mountState(ref('sim_1'))
    await flushPromises()
    expect(h_.getRun).not.toHaveBeenCalled()
    expect(api.costMicros.value).toBeNull()

    await api.adoptRunId('run_9')
    expect(h_.getRun).toHaveBeenCalledWith('run_9')
    expect(api.runId.value).toBe('run_9')
    expect(api.costMicros.value).toBe(1_500_000)
    wrapper.unmount()
  })
})
