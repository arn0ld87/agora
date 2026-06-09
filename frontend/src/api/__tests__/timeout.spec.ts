/**
 * Issue #579 — per-request timeout for long-running endpoints.
 *
 * Verifies that generateReport passes { timeout: 0 } per-call
 * (disabling the global 5-min cap) while short endpoints keep the default.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
  requestWithRetry: vi.fn(async (fn: () => Promise<unknown>) => fn()),
}))

import { generateReport } from '../report'
import { listRuns, getRun } from '../runs'

describe('#579 — generateReport uses per-call timeout: 0', () => {
  beforeEach(() => vi.clearAllMocks())

  it('passes timeout: 0 in axios config to bypass global 5-min cap', async () => {
    serviceMock.post.mockResolvedValueOnce({ success: true, data: { status: 'pending' } })

    await generateReport({ simulation_id: 'sim_abc' })

    expect(serviceMock.post).toHaveBeenCalledWith(
      '/api/report/generate',
      expect.objectContaining({ simulation_id: 'sim_abc' }),
      expect.objectContaining({ timeout: 0 }),
    )
  })

  it('does NOT override timeout for short endpoints (listRuns)', async () => {
    serviceMock.get.mockResolvedValueOnce({ success: true, data: { runs: [], total: 0, aggregation: null } })

    await listRuns()

    const [, config] = serviceMock.get.mock.calls[0]
    // listRuns should not set a per-call timeout (relies on global default)
    expect(config?.timeout).toBeUndefined()
  })

  it('does NOT override timeout for getRun (short read)', async () => {
    serviceMock.get.mockResolvedValueOnce({ success: true, data: {} })

    await getRun('run_123')

    // getRun passes no config or config without timeout override
    const callArgs = serviceMock.get.mock.calls[0]
    const config = callArgs[1]
    expect(config?.timeout).toBeUndefined()
  })
})
