/**
 * useRunsPolling — Realtime-Anbindung (#1618): solange gepollt wird, lädt
 * eine Run-Änderung sofort nach; stop() meldet ab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'

vi.mock('../../api/runs', () => ({ listRuns: vi.fn() }))
const realtime = vi.hoisted(() => ({ off: vi.fn(), reloads: [] as ((t: string) => void)[], tables: [] as string[][] }))
vi.mock('../../realtime/listInvalidation', () => ({
  onListInvalidated: vi.fn((tables: string[], reload: (t: string) => void) => {
    realtime.tables.push(tables)
    realtime.reloads.push(reload)
    return realtime.off
  }),
}))

import { listRuns } from '../../api/runs'
import { useRunsPolling } from '../useRunsPolling'

function run(id: string) {
  return {
    run_id: id,
    run_type: 'simulation_run',
    entity_id: 'sim_1',
    status: 'processing',
    progress: 10,
    message: '',
    started_at: '2026-09-26T08:00:00Z',
    updated_at: '2026-09-26T08:00:00Z',
    metadata: {},
    linked_ids: {},
    artifacts: {},
    resume_capability: {},
    summary: {},
  }
}

beforeEach(() => {
  vi.mocked(listRuns).mockReset()
  vi.mocked(listRuns).mockResolvedValue({ data: { runs: [], total: 0, aggregation: null } } as never)
  realtime.off.mockClear()
  realtime.reloads.length = 0
  realtime.tables.length = 0
})

describe('useRunsPolling + Realtime', () => {
  it('meldet sich erst mit start() an und lädt auf ein Signal nach', async () => {
    const scope = effectScope()
    const polling = scope.run(() => useRunsPolling(60_000))!
    expect(realtime.tables).toEqual([])

    await polling.start()
    await flushPromises()
    expect(realtime.tables).toEqual([['runs']])
    expect(listRuns).toHaveBeenCalledTimes(1)

    realtime.reloads[0]('runs')
    await flushPromises()
    expect(listRuns).toHaveBeenCalledTimes(2)

    polling.stop()
    expect(realtime.off).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('meldet sich bei wiederholtem start() nur einmal an', async () => {
    const scope = effectScope()
    const polling = scope.run(() => useRunsPolling(60_000))!
    await polling.start()
    await polling.start()
    expect(realtime.tables).toHaveLength(1)
    polling.stop()
    scope.stop()
  })

  it('lädt auf ein Signal auch während eines laufenden Takts und verwirft die überholte Antwort', async () => {
    let releaseOld: (v: unknown) => void = () => {}
    vi.mocked(listRuns).mockReset()
    vi.mocked(listRuns)
      .mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve }) as never)
      .mockResolvedValueOnce({ data: { runs: [run('run_neu')], total: 1, aggregation: null } } as never)
    const scope = effectScope()
    const polling = scope.run(() => useRunsPolling(60_000))!

    const started = polling.start()
    await flushPromises()
    // Takt hängt noch; das Signal darf nicht verloren gehen.
    realtime.reloads[0]('runs')
    await flushPromises()
    expect(listRuns).toHaveBeenCalledTimes(2)

    releaseOld({ data: { runs: [run('run_alt')], total: 1, aggregation: null } })
    await started
    await flushPromises()

    expect(polling.runs.value.map((r) => r.run_id)).toEqual(['run_neu'])
    expect(polling.loading.value).toBe(false)
    polling.stop()
    scope.stop()
  })
})
