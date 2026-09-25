/**
 * Erzwungene Abmeldung nach 401, integriert: echte API-Schicht (authFetch,
 * forceSignOut) und echter Auth-Store mit registriertem Callback (#1617).
 * Genau ein Abmeldeaufruf bei Supabase; scheitert er, wird der Speicher ohne
 * zweiten Netzaufruf geleert und der Store trotzdem zurückgesetzt.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'

const WS = { workspace_id: 'aaaaaaaa-0000-4000-8000-000000000001', name: 'WS', slug: 'ws', role: 'owner' as const }

const sb = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: () => {} } } })),
  refreshSession: vi.fn(),
  signOut: vi.fn(),
}))
const clearPersisted = vi.hoisted(() => vi.fn())

vi.mock('../../auth/supabaseClient', () => ({
  getSupabaseClient: vi.fn(() => ({ auth: sb })),
  initSupabaseClient: vi.fn(() => ({ auth: sb })),
  clearPersistedSession: clearPersisted,
}))
vi.mock('../../api/workspaces', () => ({
  fetchAuthConfig: vi.fn(async () => ({
    auth_backend: 'supabase',
    jwt_enabled: true,
    supabase_url: 'https://s.test',
    supabase_anon_key: 'k',
  })),
  listWorkspaces: vi.fn(async () => [WS]),
  bootstrapWorkspace: vi.fn(),
}))
const router = vi.hoisted(() => ({
  push: vi.fn(async () => {}),
  currentRoute: { value: { name: 'Shelf', fullPath: '/ablage' } },
}))
vi.mock('../../router', () => ({ default: router }))

import { authFetch } from '../../api/index'
import { getSessionToken } from '../../auth/sessionState'
import { useAuthStore } from '../auth'

beforeEach(async () => {
  setActivePinia(createPinia())
  sb.refreshSession.mockReset()
  sb.signOut.mockReset()
  clearPersisted.mockReset()
  router.push.mockClear()
  sb.getSession.mockResolvedValue({
    data: { session: { access_token: 'tok', user: { id: 'u1' }, expires_at: 9999 } },
  })
  sb.refreshSession.mockResolvedValue({ data: { session: null }, error: new Error('expired') })
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function forced401(): Promise<ReturnType<typeof useAuthStore>> {
  const store = useAuthStore()
  await store.init()
  expect(store.activeWorkspaceId).toBe(WS.workspace_id)
  await authFetch('/api/x')
  await flushPromises()
  return store
}

describe('erzwungene Abmeldung nach 401', () => {
  it('meldet genau einmal bei Supabase ab und führt zum Login', async () => {
    sb.signOut.mockResolvedValue({ error: null })

    const store = await forced401()

    expect(sb.signOut).toHaveBeenCalledTimes(1)
    expect(clearPersisted).not.toHaveBeenCalled()
    expect(store.session).toBeNull()
    expect(store.activeWorkspaceId).toBeNull()
    expect(getSessionToken()).toBeNull()
    expect(router.push).toHaveBeenCalledWith({ name: 'Login', query: { next: '/ablage' } })
  })

  it('leert bei Netzausfall den Speicher ohne zweiten Abmeldeaufruf', async () => {
    sb.signOut.mockRejectedValue(new Error('network'))

    const store = await forced401()

    expect(sb.signOut).toHaveBeenCalledTimes(1)
    expect(clearPersisted).toHaveBeenCalledTimes(1)
    expect(store.session).toBeNull()
    expect(router.push).toHaveBeenCalledWith({ name: 'Login', query: { next: '/ablage' } })
  })
})
