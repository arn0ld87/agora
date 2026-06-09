// Issue #580: listRuns return type corrected — backend envelope shape is
// { runs: RunDetail[], total: number, aggregation: RunsAggregation | null }
// not RunRecord[]. Callers must access .data.runs instead of .data.
import service from './index'
import type {
  ApiResponse,
  ListRunsParams,
  RunEvent,
  RunRecord,
} from '../types/run'
import type { RunsListResponse } from '../contracts/runsContract'

export const listRuns = (
  params: ListRunsParams = {}
): Promise<ApiResponse<RunsListResponse>> =>
  service.get('/api/runs', { params })

export const getRun = (runId: string): Promise<ApiResponse<RunRecord>> =>
  service.get(`/api/runs/${runId}`)

export const getRunEvents = (
  runId: string
): Promise<ApiResponse<RunEvent[]>> =>
  service.get(`/api/runs/${runId}/events`)

export const resumeRun = (runId: string): Promise<ApiResponse<RunRecord>> =>
  service.post(`/api/runs/${runId}/resume`)

export const stopRun = (runId: string): Promise<ApiResponse<RunRecord>> =>
  service.post(`/api/runs/${runId}/stop`)
