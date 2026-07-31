/**
 * Budget-API (Issue #764).
 *
 * Preflight-Schätzung und Verbrauchsabfragen. Alle Typen kommen aus dem
 * Zod-Spiegel (contracts/runBudgetContract) — keine duplizierten
 * Interface-Wahrheiten.
 */
import service from './index'
import type { ApiResponse } from '../types/run'
import type {
  PreflightEstimate,
  RunUsage,
} from '../contracts/runBudgetContract'

export interface PreflightEstimateParams {
  simulation_id?: string
  num_agents?: number
  max_rounds?: number
  ai_model_ref?: {
    provider_connection_id: string
    model_id: string
  }
}

/** POST /api/simulation/preflight-estimate — ehrlich gekennzeichnete Schätzung. */
export const preflightEstimate = (
  params: PreflightEstimateParams,
): Promise<ApiResponse<PreflightEstimate>> =>
  service.post('/api/simulation/preflight-estimate', params)

/** GET /api/runs/<run_id>/usage — Verbrauchsaufstellung eines Runs. */
export const getRunUsage = (
  runId: string,
): Promise<ApiResponse<RunUsage>> => service.get(`/api/runs/${runId}/usage`)
