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
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

import { getSystemStatus } from '../status'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getSystemStatus', () => {
  it('should call service.get with /api/status and return the resolved value', async () => {
    const mockResponse = {
      success: true,
      backend: { status: 'ok' },
      neo4j: { status: 'ok' },
    }
    mockGet.mockResolvedValue(mockResponse)

    const result = await getSystemStatus()

    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith('/api/status')
    expect(result).toEqual(mockResponse)
  })

  it('should propagate errors from service.get', async () => {
    const mockError = new Error('Network Error')
    mockGet.mockRejectedValue(mockError)

    await expect(getSystemStatus()).rejects.toThrow('Network Error')
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith('/api/status')
  })
})
