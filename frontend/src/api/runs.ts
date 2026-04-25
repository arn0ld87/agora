import service from './index'
import type {
  ApiResponse,
  ListRunsParams,
  RunEvent,
  RunRecord,
} from '../types/run'

export const listRuns = (
  params: ListRunsParams = {}
): Promise<ApiResponse<RunRecord[]>> =>
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
