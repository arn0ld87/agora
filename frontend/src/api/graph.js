import service, { requestWithRetry } from './index'

/**
 * Generate ontology (upload documents and simulation requirements)
 * @param {Object} data - Contains files, simulation_requirement, project_name, etc.
 * @returns {Promise}
 */
export function generateOntology(formData) {
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
 * @param {Object} data - Contains project_id, graph_name, etc.
 * @returns {Promise}
 */
export function buildGraph(data) {
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
 * @param {String} taskId - Task ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Get graph data
 * @param {String} graphId - Graph ID
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * Get project information
 * @param {String} projectId - Project ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}

/**
 * Issue #10 — Snapshot of RELATION edges valid at a given OASIS round.
 * @param {String} graphId
 * @param {Number} roundNum  zero-based round number (>=0)
 * @returns {Promise} resolves to { graph_id, round_num, edges, edge_count }
 */
export function getGraphSnapshot(graphId, roundNum) {
  return service({
    url: `/api/graph/snapshot/${graphId}/${roundNum}`,
    method: 'get'
  })
}

/**
 * Issue #10 — Diff between two rounds: added / removed / reinforced edges.
 * @param {String} graphId
 * @param {Number} startRound
 * @param {Number} endRound  must be >= startRound
 */
export function getGraphDiff(graphId, startRound, endRound) {
  return service({
    url: `/api/graph/diff/${graphId}`,
    method: 'get',
    params: { start_round: startRound, end_round: endRound }
  })
}
