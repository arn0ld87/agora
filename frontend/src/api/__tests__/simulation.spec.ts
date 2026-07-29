import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
}))

import { createSimulation, type CreateSimulationData } from '../simulation'

describe('simulation api client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('createSimulation posts to /api/simulation/create with correct data', async () => {
    const mockData: CreateSimulationData = {
      project_id: 'test-project-123',
      enable_twitter: true,
    }
    const mockResponse = { id: 'sim-123', project_id: 'test-project-123' }
    serviceMock.post.mockResolvedValueOnce(mockResponse)

    const result = await createSimulation(mockData)

    expect(serviceMock.post).toHaveBeenCalledOnce()
    expect(serviceMock.post).toHaveBeenCalledWith('/api/simulation/create', mockData)
    expect(result).toEqual(mockResponse)
  })
})
