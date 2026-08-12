// Issue #580: listRuns return type corrected — backend envelope shape is
// { runs: RunDetail[], total: number, aggregation: RunsAggregation | null }
// not RunRecord[]. Callers must access .data.runs instead of .data.
import service from './index'
import type {
  ApiResponse,
  CancelRunResponse,
  ListRunsParams,
  ReplayRequest,
  ReplayResponse,
  RunEvent,
  RunManifest,
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

export const cancelRun = (runId: string): Promise<CancelRunResponse> =>
  service.post(`/api/runs/${runId}/cancel`)

/** GET /api/runs/<run_id>/manifest — Run-Manifest abrufen (Issue #763). */
export const getRunManifest = (
  runId: string
): Promise<ApiResponse<RunManifest>> =>
  service.get(`/api/runs/${runId}/manifest`)

/**
 * POST /api/runs/<run_id>/replay — neuen Run aus Manifest starten (Issue #763).
 * Response ist flach OHNE `data`-Envelope: {run_id, status} bei 202 Accepted.
 */
export const replayRun = (
  runId: string,
  request?: ReplayRequest
): Promise<ReplayResponse> =>
  service.post(`/api/runs/${runId}/replay`, request)

/**
 * GET /api/runs/<run_id>/export — ZIP-Download mit Manifest + Artefakten
 * (Issue #763). responseType 'blob', da der Endpoint ein Binary liefert.
 */
export const exportRun = (runId: string): Promise<Blob> =>
  service.get(`/api/runs/${runId}/export`, { responseType: 'blob' })
