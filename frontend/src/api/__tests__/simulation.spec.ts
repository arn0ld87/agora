import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('../index', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args)
  }
}))

import {
  createSimulation,
  getRunStatus,
  getRunStatusDetail,
  pauseSimulation,
  prepareSimulation,
  resumeSimulation,
  startSimulation,
  stopSimulation
} from '../simulation'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('createSimulation', () => {
  it('should POST to /api/simulation/create with the payload and return the resolved value', async () => {
    const payload = { project_id: 'proj-1', graph_id: 'graph-1', enable_reddit: true }
    const mockResponse = { simulation_id: 'sim-1', project_id: 'proj-1', status: 'created' }
    mockPost.mockResolvedValue(mockResponse)

    const result = await createSimulation(payload)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/simulation/create', payload)
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.post', async () => {
    const mockError = new Error('Network Error')
    mockPost.mockRejectedValue(mockError)

    await expect(createSimulation({ project_id: 'proj-1' })).rejects.toThrow('Network Error')
    expect(mockPost).toHaveBeenCalledTimes(1)
  })
})

describe('prepareSimulation', () => {
  it('should POST to /api/simulation/prepare with the payload and return the resolved value', async () => {
    const payload = {
      simulation_id: 'sim-1',
      entity_types: ['persona'],
      use_llm_for_profiles: true,
      parallel_profile_count: 4
    }
    const mockResponse = { task_id: 'task-1', status: 'pending' }
    mockPost.mockResolvedValue(mockResponse)

    const result = await prepareSimulation(payload)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/simulation/prepare', payload)
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.post', async () => {
    const mockError = new Error('Network Error')
    mockPost.mockRejectedValue(mockError)

    await expect(prepareSimulation({ simulation_id: 'sim-1' })).rejects.toThrow('Network Error')
  })
})

describe('startSimulation', () => {
  it('should POST to /api/simulation/start with the payload and return the resolved value', async () => {
    const payload = { simulation_id: 'sim-1', platform: 'reddit' as const, max_rounds: 5 }
    const mockResponse = { simulation_id: 'sim-1', status: 'running', current_round: 0 }
    mockPost.mockResolvedValue(mockResponse)

    const result = await startSimulation(payload)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/simulation/start', payload)
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.post', async () => {
    const mockError = new Error('Network Error')
    mockPost.mockRejectedValue(mockError)

    await expect(startSimulation({ simulation_id: 'sim-1' })).rejects.toThrow('Network Error')
  })
})

describe('stopSimulation', () => {
  it('should POST to /api/simulation/stop with the payload and return the resolved value', async () => {
    const payload = { simulation_id: 'sim-1' }
    const mockResponse = { simulation_id: 'sim-1', status: 'stopped' }
    mockPost.mockResolvedValue(mockResponse)

    const result = await stopSimulation(payload)

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/simulation/stop', payload)
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.post', async () => {
    const mockError = new Error('Network Error')
    mockPost.mockRejectedValue(mockError)

    await expect(stopSimulation({ simulation_id: 'sim-1' })).rejects.toThrow('Network Error')
  })
})

describe('getRunStatus', () => {
  it('should GET /api/simulation/:id/run-status and return the resolved value', async () => {
    const mockResponse = { simulation_id: 'sim-1', status: 'running', current_round: 3 }
    mockGet.mockResolvedValue(mockResponse)

    const result = await getRunStatus('sim-1')

    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith('/api/simulation/sim-1/run-status')
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.get', async () => {
    const mockError = new Error('Network Error')
    mockGet.mockRejectedValue(mockError)

    await expect(getRunStatus('sim-1')).rejects.toThrow('Network Error')
  })
})

describe('getRunStatusDetail', () => {
  it('should GET /api/simulation/:id/run-status/detail and return the resolved value', async () => {
    const mockResponse = { simulation_id: 'sim-1', status: 'running', paused: false }
    mockGet.mockResolvedValue(mockResponse)

    const result = await getRunStatusDetail('sim-1')

    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith('/api/simulation/sim-1/run-status/detail')
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.get', async () => {
    const mockError = new Error('Network Error')
    mockGet.mockRejectedValue(mockError)

    await expect(getRunStatusDetail('sim-1')).rejects.toThrow('Network Error')
  })
})

describe('pauseSimulation', () => {
  it('should POST to /api/simulation/:id/pause without a body and return the resolved value', async () => {
    const mockResponse = { simulation_id: 'sim-1', status: 'paused', paused: true }
    mockPost.mockResolvedValue(mockResponse)

    const result = await pauseSimulation('sim-1')

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/simulation/sim-1/pause')
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.post', async () => {
    const mockError = new Error('Network Error')
    mockPost.mockRejectedValue(mockError)

    await expect(pauseSimulation('sim-1')).rejects.toThrow('Network Error')
  })
})

describe('resumeSimulation', () => {
  it('should POST to /api/simulation/:id/resume without a body and return the resolved value', async () => {
    const mockResponse = { simulation_id: 'sim-1', status: 'running', paused: false }
    mockPost.mockResolvedValue(mockResponse)

    const result = await resumeSimulation('sim-1')

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/simulation/sim-1/resume')
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.post', async () => {
    const mockError = new Error('Network Error')
    mockPost.mockRejectedValue(mockError)

    await expect(resumeSimulation('sim-1')).rejects.toThrow('Network Error')
  })
})
