/**
 * Issue #580 — listRuns return type matches backend envelope shape.
 *
 * Backend: { success: true, data: { runs, total, aggregation }, count }
 * Previous type lied: Promise<ApiResponse<RunRecord[]>> (data was RunRecord[])
 * Fixed: Promise<ApiResponse<RunsListResponse>> where RunsListResponse = { runs, total, aggregation }
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
}))

import { listRuns } from '../runs'
import type { RunsListResponse } from '../../contracts/runsContract'
import type { ApiResponse } from '../../types/run'

describe('#580 — listRuns envelope shape', () => {
  beforeEach(() => vi.clearAllMocks())

  it('resolves with correct envelope shape { runs, total, aggregation }', async () => {
    const mockEnvelope: ApiResponse<RunsListResponse> = {
      success: true,
      data: {
        runs: [],
        total: 0,
        aggregation: null,
      },
    }
    serviceMock.get.mockResolvedValueOnce(mockEnvelope)

    const result = await listRuns()

    // data should be RunsListResponse, not RunRecord[]
    expect(result.data).toHaveProperty('runs')
    expect(result.data).toHaveProperty('total')
    expect(result.data).toHaveProperty('aggregation')
    expect(Array.isArray(result.data.runs)).toBe(true)
    expect(typeof result.data.total).toBe('number')
  })

  it('resolves with runs array in data.runs (not data directly)', async () => {
    const run = {
      run_id: 'run_test',
      run_type: 'simulation_run',
      entity_id: 'sim_1',
      parent_run_id: null,
      status: 'completed',
      progress: 100,
      message: '',
      error: null,
      started_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T01:00:00Z',
      completed_at: '2026-01-01T01:00:00Z',
      branch_label: null,
      metadata: {},
      linked_ids: {},
      artifacts: {},
      resume_capability: {},
    }
    const mockEnvelope: ApiResponse<RunsListResponse> = {
      success: true,
      data: { runs: [run as any], total: 1, aggregation: null },
    }
    serviceMock.get.mockResolvedValueOnce(mockEnvelope)

    const result = await listRuns()

    expect(result.data.runs).toHaveLength(1)
    expect(result.data.runs[0].run_id).toBe('run_test')
    expect(result.data.total).toBe(1)
  })

  it('handles aggregation field when present', async () => {
    const mockEnvelope: ApiResponse<RunsListResponse> = {
      success: true,
      data: {
        runs: [],
        total: 0,
        aggregation: { counts: { completed: 5, failed: 1 }, total: 6 },
      },
    }
    serviceMock.get.mockResolvedValueOnce(mockEnvelope)

    const result = await listRuns()

    expect(result.data.aggregation).not.toBeNull()
    expect(result.data.aggregation?.counts).toEqual({ completed: 5, failed: 1 })
  })
})
