/**
 * Shared types for the run-registry API.
 *
 * Backend source of truth: backend/app/services/run_registry.py
 * (RunRegistry.create / .update_run / canonical_status). Keep field names
 * in sync with the manifest dict written there — anything we add must
 * also exist in the manifest, otherwise the type lies.
 */

export type RunType =
  | 'graph_build'
  | 'simulation_prepare'
  | 'simulation_run'
  | 'report_generate'

export type RunStatus =
  | 'pending'
  | 'processing'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'stopped'

export interface RunLinkedIds {
  project_id?: string
  simulation_id?: string
  report_id?: string
  graph_id?: string
}

export interface RunRecord {
  run_id: string
  run_type: RunType
  entity_id: string
  parent_run_id: string | null
  status: RunStatus
  progress: number
  message: string
  created_at: string
  updated_at: string
  completed_at: string | null
  branch_label: string | null
  metadata: Record<string, unknown>
  linked_ids: RunLinkedIds
}

export interface RunEvent {
  run_id: string
  ts: string
  type: string
  payload: Record<string, unknown>
}

/** Standard `{success, data, error?}` response envelope from `frontend/src/api/index.js`. */
export interface ApiResponse<T> {
  success: boolean
  data: T
  error?: string
  message?: string
  count?: number
}

export interface ListRunsParams {
  limit?: number
  entity_id?: string
  run_type?: RunType
  status?: RunStatus
}
