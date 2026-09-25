/**
 * auth store — Vitest unit tests (#1617, Part A).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

const mocks = vi.hoisted(() => {
  const _sbGetSession = vi.fn()
  const _sbOnAuthStateChange = vi.fn()
  const _sbSignOut = vi.fn()
  const _sbRefreshSession = vi.fn()
  const _svcGet = vi.fn()
  const _svcPost = vi.fn()
  const _sbSignIn = vi.fn()
  return { _sbGetSession, _sbOnAuthStateChange, _sbSignOut, _sbRefreshSession, _svcGet, _svcPost, _sbSignIn }
})

vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: mocks._sbGetSession,
      onAuthStateChange: mocks._sbOnAuthStateChange,
      signOut: mocks._sbSignOut,
      refreshSession: mocks._sbRefreshSession,
      signInWithPassword: mocks._sbSignIn,
      signUp: vi.fn(),
      updateUser: vi.fn(),
      resetPasswordForEmail: vi.fn(),
    },
  })),
}))

vi.mock('../../auth/supabaseClient', async () => {
  const { createClient } = await import('@supabase/supabase-js')
  let _client: ReturnType<typeof createClient> | null = null
  return {
    getSupabaseClient: vi.fn(() => _client),
    initSupabaseClient: vi.fn((config: { jwt_enabled: boolean; supabase_url: string | null; supabase_anon_key: string | null }) => {
      if (!config.jwt_enabled) return null
      if (!_client) _client = createClient(config.supabase_url ?? '', config.supabase_anon_key ?? '')
      return _client
    }),
    _resetSupabaseClient: vi.fn(() => { _client = null }),
  }
})

vi.mock('../../composables/useApiAuth', () => ({
  useApiAuth: { fetchTicket: vi.fn(), withFreshTicket: vi.fn(), _clearCache: vi.fn() },
}))

// Full mock: avoids interceptor/circular-import issues in test env
vi.mock('../../api/index', () => ({
  default: { get: mocks._svcGet, post: mocks._svcPost },
  getAgoraToken: vi.fn(() => ''),
  setAgoraToken: vi.fn(),
  hasCredentials: vi.fn(() => false),
  authHeaders: vi.fn(() => ({})),
  register401SignOutCallback: vi.fn(),
  requestWithRetry: vi.fn(),
}))

const routerMock = vi.hoisted(() => ({
  push: vi.fn(async () => {}),
  currentRoute: { value: { name: 'Dashboard', fullPath: '/dashboard' } },
}))
vi.mock('../../router', () => ({ default: routerMock }))

import { useApiAuth } from '../../composables/useApiAuth'
import { useAuthStore, _setReloadPage } from '../auth'
import { getSessionToken } from '../../auth/sessionState'
import { _resetSupabaseClient } from '../../auth/supabaseClient'

const WS_A = { workspace_id: 'aaaaaaaa-0000-4000-8000-000000000001', name: 'WS A', slug: 'ws-a', role: 'owner' as const }
const WS_B = { workspace_id: 'bbbbbbbb-0000-4000-8000-000000000002', name: 'WS B', slug: 'ws-b', role: 'member' as const }
const AUTH_CFG_DISABLED = { success: true, data: { auth_backend: 'legacy', jwt_enabled: false, supabase_url: null, supabase_anon_key: null } }
const AUTH_CFG_ENABLED = { success: true, data: { auth_backend: 'supabase', jwt_enabled: true, supabase_url: 'https://p.supabase.co', supabase_anon_key: 'anon' } }

beforeEach(() => {
  localStorageMock.clear()
  setActivePinia(createPinia())
  vi.clearAllMocks()
  ;(_resetSupabaseClient as unknown as () => void)()
})

describe('loadConfig()', () => {
  it('sets jwt_enabled=false in legacy mode', async () => {
    mocks._svcGet.mockResolvedValue(AUTH_CFG_DISABLED)
    const store = useAuthStore()
    await store.loadConfig()
    expect(store.jwtEnabled).toBe(false)
  })

  it('treats API failure as jwt disabled', async () => {
    mocks._svcGet.mockRejectedValue(new Error('network'))
    const store = useAuthStore()
    await store.loadConfig()
    expect(store.jwtEnabled).toBe(false)
  })

  it('parses jwt_enabled=true config', async () => {
    mocks._svcGet.mockResolvedValue(AUTH_CFG_ENABLED)
    const store = useAuthStore()
    await store.loadConfig()
    expect(store.jwtEnabled).toBe(true)
  })
})

describe('loadWorkspaces()', () => {
  it('bootstraps when list is empty and session is active', async () => {
    mocks._sbGetSession.mockResolvedValue({ data: { session: { access_token: 'tok', user: { id: 'u1' }, expires_at: 9999 } } })
    mocks._sbOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })
    mocks._svcPost.mockResolvedValueOnce({ success: true, data: WS_A })

    const store = useAuthStore()
    await store.init()

    expect(mocks._svcPost).toHaveBeenCalledWith('/api/workspaces/bootstrap', {})
    expect(store.workspaces).toHaveLength(1)
    expect(store.workspaces[0].workspace_id).toBe(WS_A.workspace_id)
  })

  it('picks persisted workspace id if still in list', async () => {
    localStorageMock.setItem('agora_workspace', WS_B.workspace_id)
    mocks._svcGet.mockResolvedValue({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()
    await store.loadWorkspaces()
    expect(store.activeWorkspaceId).toBe(WS_B.workspace_id)
  })

  it('falls back to first when persisted id not in list', async () => {
    localStorageMock.setItem('agora_workspace', 'cccccccc-0000-0000-0000-000000000099')
    mocks._svcGet.mockResolvedValue({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()
    await store.loadWorkspaces()
    expect(store.activeWorkspaceId).toBe(WS_A.workspace_id)
  })
})

describe('switchWorkspace()', () => {
  it('rejects unknown ids', async () => {
    mocks._svcGet.mockResolvedValue({ success: true, data: [WS_A] })
    const store = useAuthStore()
    await store.loadWorkspaces()
    await expect(store.switchWorkspace('unknown-id')).rejects.toThrow('unknown workspace id')
  })

  it('persists id to localStorage', async () => {
    mocks._svcGet.mockResolvedValue({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()
    await store.loadWorkspaces()
    _setReloadPage(vi.fn())
    await store.switchWorkspace(WS_B.workspace_id)
    expect(localStorageMock.getItem('agora_workspace')).toBe(WS_B.workspace_id)
  })

  it('clears the SSE ticket cache', async () => {
    mocks._svcGet.mockResolvedValue({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()
    await store.loadWorkspaces()
    _setReloadPage(vi.fn())
    await store.switchWorkspace(WS_B.workspace_id)
    expect(useApiAuth._clearCache).toHaveBeenCalled()
  })

  it('calls the reload hook', async () => {
    mocks._svcGet.mockResolvedValue({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()
    await store.loadWorkspaces()
    const reloadMock = vi.fn()
    _setReloadPage(reloadMock)
    await store.switchWorkspace(WS_A.workspace_id)
    expect(reloadMock).toHaveBeenCalled()
  })
})

describe('onAuthStateChange — session sync', () => {
  it('updates session token when SIGNED_IN fires', async () => {
    const captured: { cb: ((event: string, session: unknown) => void) | null } = { cb: null }
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._sbOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      captured.cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })

    const store = useAuthStore()
    await store.init()

    const newSession = { access_token: 'new-token-abc', user: { id: 'u2' }, expires_at: 9999 }
    captured.cb?.('SIGNED_IN', newSession)

    expect(getSessionToken()).toBe('new-token-abc')
    expect(store.session).toEqual(newSession)
  })

  it('lädt nach SIGNED_IN die Workspaces neu (Bootstrap beim ersten Login)', async () => {
    const captured: { cb: ((event: string, session: unknown) => void) | null } = { cb: null }
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._sbOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      captured.cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })
      .mockResolvedValueOnce({ success: true, data: [] })
    mocks._svcPost.mockResolvedValueOnce({ success: true, data: WS_A })

    const store = useAuthStore()
    await store.init()
    expect(mocks._svcPost).not.toHaveBeenCalled()

    captured.cb?.('SIGNED_IN', { access_token: 'tok', user: { id: 'u9' }, expires_at: 9999 })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mocks._svcPost).toHaveBeenCalledWith('/api/workspaces/bootstrap', {})
    expect(store.activeWorkspaceId).toBe(WS_A.workspace_id)
  })

  it('lädt bei TOKEN_REFRESHED keine Workspaces', async () => {
    const captured: { cb: ((event: string, session: unknown) => void) | null } = { cb: null }
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._sbOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      captured.cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_ENABLED).mockResolvedValueOnce({ success: true, data: [] })
    const store = useAuthStore()
    await store.init()
    const before = mocks._svcGet.mock.calls.length

    captured.cb?.('TOKEN_REFRESHED', { access_token: 'tok2', user: { id: 'u9' }, expires_at: 9999 })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(mocks._svcGet.mock.calls.length).toBe(before)
  })

  it('merkt sich PASSWORD_RECOVERY für die Reset-View', async () => {
    const captured: { cb: ((event: string, session: unknown) => void) | null } = { cb: null }
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._sbOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      captured.cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })

    const store = useAuthStore()
    await store.init()
    expect(store.passwordRecovery).toBe(false)

    captured.cb?.('PASSWORD_RECOVERY', { access_token: 'rec', user: { id: 'u3' }, expires_at: 9999 })

    expect(store.passwordRecovery).toBe(true)
  })

  it('startet nur einmal (ensureInit)', async () => {
    mocks._svcGet.mockResolvedValue(AUTH_CFG_DISABLED)
    const store = useAuthStore()

    await Promise.all([store.ensureInit(), store.ensureInit()])

    const configCalls = mocks._svcGet.mock.calls.filter((c) => c[0] === '/api/auth/config')
    expect(configCalls).toHaveLength(1)
  })
})

describe('Reihenfolge und Anmeldung (#1617, Codex)', () => {
  it('abonniert onAuthStateChange vor getSession()', async () => {
    const order: string[] = []
    mocks._sbOnAuthStateChange.mockImplementation(() => {
      order.push('subscribe')
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mocks._sbGetSession.mockImplementation(async () => {
      order.push('getSession')
      return { data: { session: null } }
    })
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_ENABLED).mockResolvedValueOnce({ success: true, data: [] })

    await useAuthStore().init()

    expect(order).toEqual(['subscribe', 'getSession'])
  })

  it('signIn kehrt erst mit gewähltem Workspace zurück', async () => {
    mocks._sbOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })
      .mockResolvedValueOnce({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()
    await store.init()
    mocks._sbSignIn.mockResolvedValue({
      data: { session: { access_token: 'tok-signin', user: { id: 'u1' }, expires_at: 9999 } },
      error: null,
    })

    await store.signIn('a@example.test', 'ein-langes-passwort')

    expect(getSessionToken()).toBe('tok-signin')
    expect(store.activeWorkspaceId).toBe(WS_A.workspace_id)
  })

  it('bündelt gleichzeitige loadWorkspaces-Aufrufe', async () => {
    let release: (v: unknown) => void = () => {}
    mocks._svcGet.mockReturnValueOnce(new Promise((r) => { release = r }))
    const store = useAuthStore()

    const first = store.loadWorkspaces()
    const second = store.loadWorkspaces()
    release({ success: true, data: [WS_A] })
    await Promise.all([first, second])

    const listCalls = mocks._svcGet.mock.calls.filter((c) => c[0] === '/api/workspaces')
    expect(listCalls).toHaveLength(1)
    expect(store.activeWorkspaceId).toBe(WS_A.workspace_id)
  })
})

describe('Codex-Runde 2 (#1617)', () => {
  function jwtStore() {
    mocks._sbOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._sbSignIn.mockResolvedValue({
      data: { session: { access_token: 'tok-signin', user: { id: 'u1' }, expires_at: 9999 } },
      error: null,
    })
  }

  it('signIn scheitert, wenn die Workspace-Liste nicht ladbar ist', async () => {
    jwtStore()
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })
      .mockRejectedValueOnce(new Error('network'))
    const store = useAuthStore()
    await store.init()

    await expect(store.signIn('a@example.test', 'ein-langes-passwort')).rejects.toThrow()
    expect(store.activeWorkspaceId).toBeNull()
  })

  it('signIn scheitert, wenn der Bootstrap scheitert', async () => {
    jwtStore()
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })
      .mockResolvedValueOnce({ success: true, data: [] })
    mocks._svcPost.mockResolvedValueOnce({ success: false, code: 'rate_limited', error: 'rate limited' })
    const store = useAuthStore()
    await store.init()

    await expect(store.signIn('a@example.test', 'ein-langes-passwort')).rejects.toThrow()
  })

  it('verwirft eine Workspace-Liste, die nicht dem Vertrag entspricht', async () => {
    mocks._svcGet.mockResolvedValueOnce({ success: true, data: [{ workspace_id: 'kein-uuid', name: 'x', slug: 'x', role: 'owner' }] })
    const store = useAuthStore()

    await expect(store.loadWorkspaces()).rejects.toThrow()
    expect(store.activeWorkspaceId).toBeNull()
  })

  it('zählt im Modus supabase nur die Session, nicht den Legacy-Token', async () => {
    const { getAgoraToken } = await import('../../api/index')
    vi.mocked(getAgoraToken).mockReturnValue('alter-master-token')
    mocks._svcGet.mockResolvedValueOnce({
      success: true,
      data: { auth_backend: 'supabase', jwt_enabled: true, supabase_url: 'https://p.supabase.co', supabase_anon_key: 'anon' },
    })
    const store = useAuthStore()
    await store.loadConfig()

    expect(store.isAuthenticated).toBe(false)
    vi.mocked(getAgoraToken).mockReturnValue('')
  })

  it('zählt im Modus hybrid den Legacy-Token weiter', async () => {
    const { getAgoraToken } = await import('../../api/index')
    vi.mocked(getAgoraToken).mockReturnValue('master-token')
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_DISABLED)
    const store = useAuthStore()
    await store.loadConfig()

    expect(store.isAuthenticated).toBe(true)
    vi.mocked(getAgoraToken).mockReturnValue('')
  })
})

describe('Codex-Runde 3 (#1617)', () => {
  it('beendet eine wiederhergestellte Session, deren Workspace-Start scheitert', async () => {
    mocks._sbOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    mocks._sbGetSession.mockResolvedValue({
      data: { session: { access_token: 'restored', user: { id: 'u1' }, expires_at: 9999 } },
    })
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_ENABLED).mockRejectedValueOnce(new Error('network'))
    const store = useAuthStore()

    await store.init()

    expect(mocks._sbSignOut).toHaveBeenCalledTimes(1)
    expect(store.session).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(getSessionToken()).toBeNull()
  })

  it('behält eine wiederhergestellte Session mit aktivem Workspace', async () => {
    mocks._sbOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    mocks._sbGetSession.mockResolvedValue({
      data: { session: { access_token: 'restored', user: { id: 'u1' }, expires_at: 9999 } },
    })
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_ENABLED).mockResolvedValueOnce({ success: true, data: [WS_A, WS_B] })
    const store = useAuthStore()

    await store.init()

    expect(mocks._sbSignOut).not.toHaveBeenCalled()
    expect(store.isAuthenticated).toBe(true)
    expect(store.activeWorkspaceId).toBe(WS_A.workspace_id)
  })

  it('SIGNED_OUT leert den Workspace-Zustand und führt zum Login', async () => {
    const captured: { cb: ((event: string, session: unknown) => void) | null } = { cb: null }
    mocks._sbOnAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      captured.cb = cb
      return { data: { subscription: { unsubscribe: vi.fn() } } }
    })
    mocks._sbGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok', user: { id: 'u1' }, expires_at: 9999 } },
    })
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_ENABLED).mockResolvedValueOnce({ success: true, data: [WS_A] })
    const store = useAuthStore()
    await store.init()
    routerMock.push.mockClear()

    captured.cb?.('SIGNED_OUT', null)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(store.workspaces).toEqual([])
    expect(store.activeWorkspaceId).toBeNull()
    expect(getSessionToken()).toBeNull()
    expect(routerMock.push).toHaveBeenCalledWith({ name: 'Login', query: { next: '/dashboard' } })
  })

  it('gewährt Betreiber-Zugang nur ohne Supabase-Session', async () => {
    mocks._svcGet.mockResolvedValueOnce(AUTH_CFG_ENABLED)
    const store = useAuthStore()
    await store.loadConfig()
    expect(store.operatorAccess).toBe(true)

    store.session = { access_token: 'x' } as never

    expect(store.operatorAccess).toBe(false)
  })
})

describe('Codex-Runde 4 (#1617)', () => {
  it('meldet ab, wenn signIn am Workspace scheitert', async () => {
    mocks._sbOnAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
    mocks._sbGetSession.mockResolvedValue({ data: { session: null } })
    mocks._sbSignIn.mockResolvedValue({
      data: { session: { access_token: 'tok-signin', user: { id: 'u1' }, expires_at: 9999 } },
      error: null,
    })
    mocks._svcGet
      .mockResolvedValueOnce(AUTH_CFG_ENABLED)
      .mockResolvedValueOnce({ success: true, data: [] })
      .mockRejectedValueOnce(new Error('network'))
    const store = useAuthStore()
    await store.init()

    await expect(store.signIn('a@example.test', 'ein-langes-passwort')).rejects.toThrow()

    expect(mocks._sbSignOut).toHaveBeenCalledTimes(1)
    expect(store.session).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(getSessionToken()).toBeNull()
  })
})
