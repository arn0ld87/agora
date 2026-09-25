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
})
