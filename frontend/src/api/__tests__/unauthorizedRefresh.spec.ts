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

import service, { authFetch, register401SignOutCallback } from '../index'
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
    expect(retry).toHaveBeenCalledWith({ ...config, _agoraAuthRetried: true })
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

  it('does not refresh again when the retry (a cloned config) gets a 401', async () => {
    sb.refreshSession.mockResolvedValue({ data: { session: { access_token: 'new-token' } }, error: null })
    const retry = vi.spyOn(service, 'request').mockResolvedValue('retried' as never)
    await rejectedHandler()(unauthorized({ url: '/api/z' }))
    sb.refreshSession.mockClear()
    // Axios klont die Config: der zweite 401 trägt ein neues Objekt.
    const retriedConfig = { ...(retry.mock.calls[0][0] as object) }

    await expect(rejectedHandler()(unauthorized(retriedConfig))).rejects.toBeTruthy()

    expect(sb.refreshSession).not.toHaveBeenCalled()
    expect(retry).toHaveBeenCalledTimes(1)
  })

  it('shares one refresh between concurrent 401s', async () => {
    let resolveRefresh: (v: unknown) => void = () => {}
    sb.refreshSession.mockReturnValue(new Promise((r) => { resolveRefresh = r }))
    vi.spyOn(service, 'request').mockResolvedValue('retried' as never)

    const a = rejectedHandler()(unauthorized({ url: '/api/a' }))
    const b = rejectedHandler()(unauthorized({ url: '/api/b' }))
    await new Promise((r) => setTimeout(r, 0))
    resolveRefresh({ data: { session: { access_token: 'new-token' } }, error: null })

    await expect(Promise.all([a, b])).resolves.toEqual(['retried', 'retried'])
    expect(sb.refreshSession).toHaveBeenCalledTimes(1)
  })

  it('leaves legacy token mode alone', async () => {
    setSessionToken(null)

    await expect(rejectedHandler()(unauthorized({ url: '/api/legacy' }))).rejects.toBeTruthy()

    expect(sb.refreshSession).not.toHaveBeenCalled()
    expect(sb.signOut).not.toHaveBeenCalled()
  })
})

describe('authFetch()', () => {
  it('refreshes once on 401 and retries with the new token', async () => {
    sb.refreshSession.mockResolvedValue({ data: { session: { access_token: 'fresh' } }, error: null })
    const seen: string[] = []
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      const auth = (init?.headers as Record<string, string>)['Authorization']
      seen.push(auth)
      return new Response('{}', { status: auth === 'Bearer fresh' ? 200 : 401 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const res = await authFetch('/api/graph/g/diff')

    expect(res.status).toBe(200)
    expect(seen).toEqual(['Bearer old-token', 'Bearer fresh'])
    vi.unstubAllGlobals()
  })

  it('signs out when the refresh fails', async () => {
    sb.refreshSession.mockResolvedValue({ data: { session: null }, error: new Error('expired') })
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
    const onSignOut = vi.fn()
    register401SignOutCallback(onSignOut)

    const res = await authFetch('/api/x')

    expect(res.status).toBe(401)
    expect(sb.signOut).toHaveBeenCalledTimes(1)
    expect(onSignOut).toHaveBeenCalledTimes(1)
    expect(getSessionToken()).toBeNull()
    vi.unstubAllGlobals()
  })

  it('leaves legacy mode alone', async () => {
    setSessionToken(null)
    const fetchMock = vi.fn(async () => new Response('{}', { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    await authFetch('/api/x')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(sb.refreshSession).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
