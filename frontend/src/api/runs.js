import service from './index'

export const listRuns = (params = {}) => service.get('/api/runs', { params })

export const getRun = (runId) => service.get(`/api/runs/${runId}`)

export const getRunEvents = (runId) => service.get(`/api/runs/${runId}/events`)

export const resumeRun = (runId) => service.post(`/api/runs/${runId}/resume`)

export const stopRun = (runId) => service.post(`/api/runs/${runId}/stop`)
