import service, { requestWithRetry } from './index'
import type { ApiResponse } from '../types/run'

// --- Local types --------------------------------------------------------

export interface BuildGraphData {
  project_id: string
  graph_name?: string
  [key: string]: unknown
}

export interface BuildProgressDetail {
  batch_count: number
  total_batches: number
  batch_at: number
}

export interface BuildGraphResponse {
  task_id: string
}

export interface TaskStatusResponse {
  task_id: string
  status: string
  progress?: number
  message?: string
  error?: string | null
  result?: Record<string, unknown> | null
  progress_detail?: BuildProgressDetail | null
}

export interface GraphDataResponse {
  graph_id: string
  nodes: unknown[]
  edges: unknown[]
  [key: string]: unknown
}

export interface ProjectResponse {
  project_id: string
  project_name?: string
  status?: string
  graph_id?: string
  graph_build_task_id?: string
  [key: string]: unknown
}

export interface GraphSnapshotResponse {
  graph_id: string
  round_num: number
  edges: unknown[]
  edge_count: number
}

export interface GraphDiffResponse {
  graph_id: string
  start_round: number
  end_round: number
  added: unknown[]
  removed: unknown[]
  reinforced: unknown[]
}

// --- API functions -------------------------------------------------------

/**
 * Generate ontology (upload documents and simulation requirements)
 * @param formData - Contains files, simulation_requirement, project_name, etc.
 */
export function generateOntology(formData: FormData): Promise<ApiResponse<ProjectResponse>> {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * Build graph
 * @param data - Contains project_id, graph_name, etc.
 */
export function buildGraph(data: BuildGraphData): Promise<ApiResponse<BuildGraphResponse>> {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * Query task status
 * @param taskId - Task ID
 */
export function getTaskStatus(taskId: string): Promise<ApiResponse<TaskStatusResponse>> {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Get graph data
 * @param graphId - Graph ID
 */
export function getGraphData(graphId: string): Promise<ApiResponse<GraphDataResponse>> {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * Get project information
 * @param projectId - Project ID
 */
export function getProject(projectId: string): Promise<ApiResponse<ProjectResponse>> {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}

/**
 * Issue #10 — Snapshot of RELATION edges valid at a given OASIS round.
 * @param graphId
 * @param roundNum - zero-based round number (>=0)
 * @returns resolves to { graph_id, round_num, edges, edge_count }
 */
export function getGraphSnapshot(
  graphId: string,
  roundNum: number
): Promise<GraphSnapshotResponse> {
  return service({
    url: `/api/graph/snapshot/${graphId}/${roundNum}`,
    method: 'get'
  })
}

/**
 * Issue #10 — Diff between two rounds: added / removed / reinforced edges.
 * @param graphId
 * @param startRound
 * @param endRound - must be >= startRound
 */
export function getGraphDiff(
  graphId: string,
  startRound: number,
  endRound: number
): Promise<GraphDiffResponse> {
  return service({
    url: `/api/graph/diff/${graphId}`,
    method: 'get',
    params: { start_round: startRound, end_round: endRound }
  })
}

/**
 * Slice 5.3 — GraphML export of the full graph.
 * Returns a Blob via axios; consumers handle attachment download.
 * @param graphId
 */
export function exportGraphMl(graphId: string): Promise<Blob> {
  return service({
    url: `/api/graph/${graphId}/export`,
    method: 'get',
    params: { format: 'graphml' },
    responseType: 'blob'
  })
}
