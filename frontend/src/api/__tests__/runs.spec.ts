import { beforeEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('../index', () => ({
  default: serviceMock,
}))

import { cancelRun, exportRun, getRunManifest, replayRun, resumeRun, stopRun } from '../runs'

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

  // Issue #763 (Ticket 8/6): Replay + Export + Manifest-Abruf.
  it('replayRun posts to /api/runs/<id>/replay without body for identical replay', async () => {
    const mockResponse = { run_id: 'run-new', status: 'pending' }
    serviceMock.post.mockResolvedValueOnce(mockResponse)

    const result = await replayRun('run-orig')

    expect(serviceMock.post).toHaveBeenCalledWith('/api/runs/run-orig/replay', undefined)
    expect(result).toEqual(mockResponse)
  })

  it('replayRun posts overrides for variant replay', async () => {
    serviceMock.post.mockResolvedValueOnce({ run_id: 'run-new', status: 'pending' })

    await replayRun('run-orig', { overrides: { random_seed: 42 } })

    expect(serviceMock.post).toHaveBeenCalledWith('/api/runs/run-orig/replay', {
      overrides: { random_seed: 42 },
    })
  })

  it('exportRun gets /api/runs/<id>/export as blob', async () => {
    const mockBlob = new Blob(['zip-bytes'])
    serviceMock.get.mockResolvedValueOnce(mockBlob)

    const result = await exportRun('run-abc')

    expect(serviceMock.get).toHaveBeenCalledWith('/api/runs/run-abc/export', {
      responseType: 'blob',
    })
    expect(result).toBe(mockBlob)
  })

  it('getRunManifest gets /api/runs/<id>/manifest', async () => {
    const mockManifest = { success: true, data: { run_id: 'run-abc', status: 'final' } }
    serviceMock.get.mockResolvedValueOnce(mockManifest)

    const result = await getRunManifest('run-abc')

    expect(serviceMock.get).toHaveBeenCalledWith('/api/runs/run-abc/manifest')
    expect(result).toEqual(mockManifest)
  })
})
