import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
}))

import { cancelRun, resumeRun, stopRun } from '../runs'

describe('runs api client', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('cancelRun posts to /api/runs/<id>/cancel and returns flat CancelRunResponse (no data envelope)', async () => {
    // Backend returns 202 with {"success": true, "status": "cancel_requested", "run_id": "..."}
    // — no wrapping `data` key (backend/app/api/runs.py:391).
    const mockResponse: { success: true; status: 'cancel_requested'; run_id: string } = {
      success: true,
      status: 'cancel_requested',
      run_id: 'run-abc',
    }
    serviceMock.post.mockResolvedValueOnce(mockResponse)

    const result = await cancelRun('run-abc')

    expect(serviceMock.post).toHaveBeenCalledOnce()
    expect(serviceMock.post).toHaveBeenCalledWith('/api/runs/run-abc/cancel')
    expect(result).toEqual(mockResponse)
  })

  it('stopRun posts to /api/runs/<id>/stop', async () => {
    serviceMock.post.mockResolvedValueOnce({ success: true, data: { run_id: 'run-xyz', status: 'stopped' } })
    await stopRun('run-xyz')
    expect(serviceMock.post).toHaveBeenCalledWith('/api/runs/run-xyz/stop')
  })

  it('resumeRun posts to /api/runs/<id>/resume', async () => {
    serviceMock.post.mockResolvedValueOnce({ success: true, data: { run_id: 'run-xyz', status: 'processing' } })
    await resumeRun('run-xyz')
    expect(serviceMock.post).toHaveBeenCalledWith('/api/runs/run-xyz/resume')
  })
})
