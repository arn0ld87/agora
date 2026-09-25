/**
 * auth — Pinia-Store für Supabase-JWT-Auth + Legacy-Token-Kompatibilität (#1617).
 *
 * - loadConfig(): GET /api/auth/config, Zod-parse; bei Fehler → Legacy-Modus.
 * - init(): loadConfig + Session-Sync + loadWorkspaces.
 * - signIn/signUp/signOut/requestPasswordReset/updatePassword: Supabase-Auth.
 * - loadWorkspaces(): GET /api/workspaces; bootstrapt leer; wählt persistierten ws.
 * - switchWorkspace(): validiert, persistiert, leert Ticket-Cache, reload.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { Session, User } from '@supabase/supabase-js'

import service, { getAgoraToken, register401SignOutCallback } from '../api/index'
import { setSessionToken, setActiveWorkspaceId } from '../auth/sessionState'
import { initSupabaseClient, getSupabaseClient } from '../auth/supabaseClient'
import { AuthConfigResponseSchema, type AuthConfigResponse } from '../contracts/authConfigContract'
import { WorkspaceSummarySchema, type WorkspaceSummary } from '../contracts/workspaceContract'
import { useApiAuth } from '../composables/useApiAuth'

// Isolierter Reload-Hook — testbar, da überschreibbar.
export let _reloadPage: () => void = () => {
  window.location.reload()
}

/** Nur für Tests: Reload-Funktion überschreiben. */
export function _setReloadPage(fn: () => void): void {
  _reloadPage = fn
}

const WORKSPACE_STORAGE_KEY = 'agora_workspace'

function _readPersistedWorkspaceId(): string | null {
  try {
    return window.localStorage.getItem(WORKSPACE_STORAGE_KEY)
  } catch {
    return null
  }
}

function _persistWorkspaceId(id: string | null): void {
  try {
    if (id) {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, id)
    } else {
      window.localStorage.removeItem(WORKSPACE_STORAGE_KEY)
    }
  } catch {
    // ignore quota or security errors
  }
}

interface WorkspacesEnvelope {
  data?: unknown
}

export const useAuthStore = defineStore('auth', () => {
  // --- State ---
  const config = ref<AuthConfigResponse | null>(null)
  const session = ref<Session | null>(null)
  const user = ref<User | null>(null)
  const workspaces = ref<WorkspaceSummary[]>([])
  const activeWorkspaceId = ref<string | null>(null)
  // Supabase meldet PASSWORD_RECOVERY beim Einlesen des Reset-Links, also
  // schon beim Init — vor dem Mount der Reset-View. Deshalb hält der Store es.
  const passwordRecovery = ref(false)

  // --- Computed ---
  const jwtEnabled = computed(() => config.value?.jwt_enabled ?? false)

  const isAuthenticated = computed(
    () => !!(getAgoraToken() || session.value),
  )

  const tokenExpiry = computed<number | null>(() => {
    if (!session.value?.expires_at) return null
    return session.value.expires_at
  })

  const roles = computed<Record<string, string>>(() => {
    const map: Record<string, string> = {}
    for (const ws of workspaces.value) {
      map[ws.workspace_id] = ws.role
    }
    return map
  })

  // --- Actions ---

  async function loadConfig(): Promise<void> {
    try {
      const raw = await service.get('/api/auth/config')
      const parsed = AuthConfigResponseSchema.safeParse(
        (raw as { data?: unknown })?.data ?? raw,
      )
      if (!parsed.success) {
        // Treat as jwt disabled (legacy behaviour unchanged)
        config.value = { auth_backend: 'legacy', jwt_enabled: false, supabase_url: null, supabase_anon_key: null }
        return
      }
      config.value = parsed.data
    } catch {
      // On failure treat as jwt disabled — legacy behaviour unchanged.
      config.value = { auth_backend: 'legacy', jwt_enabled: false, supabase_url: null, supabase_anon_key: null }
    }
  }

  async function init(): Promise<void> {
    await loadConfig()

    if (jwtEnabled.value && config.value) {
      const supabase = initSupabaseClient(config.value)
      if (supabase) {
        const { data } = await supabase.auth.getSession()
        session.value = data.session
        user.value = data.session?.user ?? null
        if (data.session?.access_token) {
          setSessionToken(data.session.access_token)
        }

        supabase.auth.onAuthStateChange((event, newSession) => {
          if (event === 'PASSWORD_RECOVERY') passwordRecovery.value = true
          session.value = newSession
          user.value = newSession?.user ?? null
          setSessionToken(newSession?.access_token ?? null)
          if (event === 'SIGNED_IN') {
            // Nach der Anmeldung (Formular oder Bestätigungslink) die eigenen
            // Workspaces laden, beim ersten Mal mit Bootstrap. Außerhalb des
            // Callbacks, weil supabase-js darin keine weiteren Aufrufe mag.
            setTimeout(() => { void loadWorkspaces() }, 0)
          }
        })

        // Register 401 callback: on forced signOut, redirect to Login.
        register401SignOutCallback(() => {
          void signOut()
          // Router redirect happens inside signOut or via the route guard.
          // Use dynamic import to avoid circular store→router dependency.
          import('../router').then((m) => {
            const router = m.default
            if (router) {
              router.push({ name: 'Login', query: { next: window.location.pathname } }).catch(() => {/* route may not exist yet in part A */})
            }
          }).catch(() => {/* ignore */})
        })
      }
    }

    await loadWorkspaces()
  }

  // Einmaliger Start: der Router-Guard wartet darauf, bevor er die erste
  // Navigation entscheidet (app.use(router) navigiert sofort).
  let initPromise: Promise<void> | null = null
  function ensureInit(): Promise<void> {
    if (!initPromise) {
      initPromise = init().catch(() => {
        // Fehler beim Auth-Init — Legacy-Verhalten bleibt.
      })
    }
    return initPromise
  }

  async function signIn(email: string, password: string): Promise<void> {
    const supabase = getSupabaseClient()
    if (!supabase) throw new Error('Supabase not initialised (jwt_enabled=false)')
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
  }

  async function signUp(email: string, password: string): Promise<void> {
    const supabase = getSupabaseClient()
    if (!supabase) throw new Error('Supabase not initialised (jwt_enabled=false)')
    const emailRedirectTo = `${window.location.origin}/auth/confirm`
    const { error } = await supabase.auth.signUp({ email, password, options: { emailRedirectTo } })
    if (error) throw error
  }

  async function signOut(): Promise<void> {
    const supabase = getSupabaseClient()
    if (supabase) {
      await supabase.auth.signOut()
    }
    session.value = null
    user.value = null
    setSessionToken(null)
  }

  async function requestPasswordReset(email: string): Promise<void> {
    const supabase = getSupabaseClient()
    if (!supabase) throw new Error('Supabase not initialised (jwt_enabled=false)')
    const redirectTo = `${window.location.origin}/auth/reset`
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo })
    if (error) throw error
  }

  async function updatePassword(password: string): Promise<void> {
    const supabase = getSupabaseClient()
    if (!supabase) throw new Error('Supabase not initialised (jwt_enabled=false)')
    const { error } = await supabase.auth.updateUser({ password })
    if (error) throw error
    passwordRecovery.value = false
  }

  async function loadWorkspaces(): Promise<void> {
    try {
      const raw = (await service.get('/api/workspaces')) as WorkspacesEnvelope
      const payload = (raw as { data?: unknown })?.data ?? raw
      const list = Array.isArray(payload) ? payload : (payload as { data?: unknown })?.data

      const parsed: WorkspaceSummary[] = []
      if (Array.isArray(list)) {
        for (const item of list) {
          const r = WorkspaceSummarySchema.safeParse(item)
          if (r.success) parsed.push(r.data)
        }
      }

      // If JWT session and list is empty → bootstrap a default workspace.
      if (parsed.length === 0 && session.value) {
        try {
          const bootstrapRaw = (await service.post('/api/workspaces/bootstrap', {})) as { data?: unknown }
          const bootstrapPayload = bootstrapRaw?.data ?? bootstrapRaw
          const r = WorkspaceSummarySchema.safeParse(bootstrapPayload)
          if (r.success) parsed.push(r.data)
        } catch {
          // Bootstrap failed — proceed without workspace
        }
      }

      workspaces.value = parsed

      // Choose workspace: prefer persisted id if it's still in the list, else first.
      const persisted = _readPersistedWorkspaceId()
      const still = persisted ? parsed.find((w) => w.workspace_id === persisted) : undefined
      const chosen = still ?? parsed[0] ?? null
      activeWorkspaceId.value = chosen?.workspace_id ?? null
      setActiveWorkspaceId(activeWorkspaceId.value)
    } catch {
      // Network error — keep existing state
    }
  }

  async function switchWorkspace(id: string): Promise<void> {
    const found = workspaces.value.find((w) => w.workspace_id === id)
    if (!found) {
      throw new Error(`switchWorkspace: unknown workspace id "${id}"`)
    }
    activeWorkspaceId.value = id
    setActiveWorkspaceId(id)
    _persistWorkspaceId(id)
    useApiAuth._clearCache()
    _reloadPage()
  }

  return {
    // state
    config,
    session,
    user,
    workspaces,
    activeWorkspaceId,
    passwordRecovery,
    // computed
    jwtEnabled,
    isAuthenticated,
    tokenExpiry,
    roles,
    // actions
    loadConfig,
    init,
    ensureInit,
    signIn,
    signUp,
    signOut,
    requestPasswordReset,
    updatePassword,
    loadWorkspaces,
    switchWorkspace,
  }
})
