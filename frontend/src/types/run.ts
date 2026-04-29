/**
 * Shared types for the run-registry API.
 *
 * Backend source of truth: backend/app/services/run_registry.py
 * (RunRegistry.create / .update_run / canonical_status) for the manifest, and
 * backend/app/api/runs.py (`_build_run_summary`) for the read-path
 * `summary` block. Keep field names in sync — anything we add here must
 * exist either in the manifest or in the API enrichment, otherwise the
 * type lies.
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
  task_id?: string
}

export interface RunResumeCapability {
  available?: boolean
  action?: string | null
  label?: string | null
}

export interface RunArtifacts {
  simulation?: Record<string, string>
  report?: Record<string, string>
  project_dir?: Record<string, string>
  [key: string]: Record<string, string> | undefined
}

export interface RunSummary {
  model: string | null
  document_name: string | null
  persona_count: number | null
  graph_id: string | null
  graph_name: string | null
  branch_name: string | null
}

export interface RunRecord {
  run_id: string
  run_type: RunType
  entity_id: string
  parent_run_id: string | null
  status: RunStatus
  progress: number
  message: string
  error: string | null
  started_at: string
  updated_at: string
  completed_at: string | null
  branch_label: string | null
  metadata: Record<string, unknown>
  linked_ids: RunLinkedIds
  artifacts: RunArtifacts
  resume_capability: RunResumeCapability
  /** Read-path enrichment from `/api/runs` and `/api/runs/<id>` (Slice 3.1). */
  summary?: RunSummary
}

export interface RunEvent {
  timestamp: string
  type: string
  status?: RunStatus
  progress?: number | null
  message?: string
  error?: string | null
  details?: Record<string, unknown>
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
  project?: string
  branch?: string
}
