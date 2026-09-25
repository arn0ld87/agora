/**
 * 401 mit Supabase-Session: einmal refreshSession + Retry, sonst signOut (#1617).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const sb = vi.hoisted(() => ({
  refreshSession: vi.fn(),
  signOut: vi.fn(),
}))

vi.mock('../../auth/supabaseClient', () => ({
  getSupabaseClient: vi.fn(() => ({ auth: sb })),
}))

import service, { register401SignOutCallback } from '../index'
import { getSessionToken, setSessionToken } from '../../auth/sessionState'

type Rejected = (error: unknown) => Promise<unknown>

function rejectedHandler(): Rejected {
  const handlers = (service.interceptors.response as unknown as {
    handlers: Array<{ rejected: Rejected } | null>
  }).handlers
  const handler = handlers.find((h) => h !== null)
  if (!handler) throw new Error('no response interceptor')
  return handler.rejected
}

function unauthorized(config: object) {
  return { response: { status: 401, data: { success: false, error: 'invalid_token', code: 'invalid_token' } }, config }
}

beforeEach(() => {
  vi.restoreAllMocks()
  sb.refreshSession.mockReset()
  sb.signOut.mockReset()
  setSessionToken('old-token')
  register401SignOutCallback(() => {})
})

describe('401 mit Supabase-Session', () => {
  it('refreshes once, stores the new token and retries', async () => {
    sb.refreshSession.mockResolvedValue({ data: { session: { access_token: 'new-token' } }, error: null })
    const retry = vi.spyOn(service, 'request').mockResolvedValue('retried' as never)
    const config = { url: '/api/x' }

    const result = await rejectedHandler()(unauthorized(config))

    expect(result).toBe('retried')
    expect(sb.refreshSession).toHaveBeenCalledTimes(1)
    expect(getSessionToken()).toBe('new-token')
    expect(retry).toHaveBeenCalledWith(config)
  })

  it('signs out when the refresh fails and does not retry', async () => {
    sb.refreshSession.mockResolvedValue({ data: { session: null }, error: new Error('expired') })
    const retry = vi.spyOn(service, 'request')
    const onSignOut = vi.fn()
    register401SignOutCallback(onSignOut)

    await expect(rejectedHandler()(unauthorized({ url: '/api/y' }))).rejects.toBeTruthy()

    expect(retry).not.toHaveBeenCalled()
    expect(sb.signOut).toHaveBeenCalledTimes(1)
    expect(onSignOut).toHaveBeenCalledTimes(1)
    expect(getSessionToken()).toBeNull()
  })

  it('does not refresh a request that was already retried', async () => {
    sb.refreshSession.mockResolvedValue({ data: { session: { access_token: 'new-token' } }, error: null })
    vi.spyOn(service, 'request').mockResolvedValue('retried' as never)
    const config = { url: '/api/z' }
    await rejectedHandler()(unauthorized(config))
    sb.refreshSession.mockClear()

    await expect(rejectedHandler()(unauthorized(config))).rejects.toBeTruthy()

    expect(sb.refreshSession).not.toHaveBeenCalled()
  })

  it('leaves legacy token mode alone', async () => {
    setSessionToken(null)

    await expect(rejectedHandler()(unauthorized({ url: '/api/legacy' }))).rejects.toBeTruthy()

    expect(sb.refreshSession).not.toHaveBeenCalled()
    expect(sb.signOut).not.toHaveBeenCalled()
  })
})
