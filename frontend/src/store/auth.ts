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

import { getAgoraToken, register401SignOutCallback } from '../api/index'
import { bootstrapWorkspace, fetchAuthConfig, listWorkspaces } from '../api/workspaces'
import { setSessionToken, setActiveWorkspaceId } from '../auth/sessionState'
import { initSupabaseClient, getSupabaseClient } from '../auth/supabaseClient'
import type { AuthConfigResponse } from '../contracts/authConfigContract'
import type { WorkspaceSummary } from '../contracts/workspaceContract'
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

  // Im Modus `supabase` lehnt das Backend den Master-Token ab: dort zählt
  // nur eine Session. `hybrid`/`legacy` akzeptieren weiter den Token.
  const isAuthenticated = computed(() => {
    if (session.value) return true
    if (config.value?.auth_backend === 'supabase') return false
    return !!getAgoraToken()
  })

  /** Betreiber-Zugang: Legacy-Token oder offener Modus, keine Supabase-Session.
   *  Prozessweite Bereiche (Logs, Einstellungen) sind für JWT gesperrt. */
  const operatorAccess = computed(() => !(jwtEnabled.value && session.value))

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

  const LEGACY_CONFIG: AuthConfigResponse = {
    auth_backend: 'legacy',
    jwt_enabled: false,
    supabase_url: null,
    supabase_anon_key: null,
  }

  async function loadConfig(): Promise<void> {
    try {
      config.value = await fetchAuthConfig()
    } catch {
      // Nicht erreichbar oder ungültig: JWT aus, Legacy-Verhalten unverändert.
      config.value = LEGACY_CONFIG
    }
  }

  async function init(): Promise<void> {
    await loadConfig()

    if (jwtEnabled.value && config.value) {
      const supabase = initSupabaseClient(config.value)
      if (supabase) {
        // Erst abonnieren, dann getSession(): der Client liest beim Init die
        // URL (Bestätigungs- oder Reset-Link) und meldet PASSWORD_RECOVERY
        // bzw. SIGNED_IN, bevor getSession() zurückkehrt.
        supabase.auth.onAuthStateChange((event, newSession) => {
          if (event === 'PASSWORD_RECOVERY') passwordRecovery.value = true
          if (event === 'SIGNED_OUT') {
            // Auch aus einem anderen Tab: Workspace-Zustand verwerfen und die
            // geschützte Ansicht verlassen.
            clearWorkspaceState()
            setTimeout(() => { void goToLogin() }, 0)
          }
          session.value = newSession
          user.value = newSession?.user ?? null
          setSessionToken(newSession?.access_token ?? null)
          if (event === 'SIGNED_IN') {
            // Anmeldung über einen Link: Workspaces nachladen. Außerhalb des
            // Callbacks, weil supabase-js darin keine weiteren Aufrufe mag;
            // loadWorkspaces() bündelt gleichzeitige Aufrufe.
            setTimeout(() => {
              loadWorkspaces().catch(() => {
                // Fehlt der Workspace, lehnen Folgeanfragen ab; der nächste
                // Login oder Seitenaufruf lädt erneut.
              })
            }, 0)
          }
        })

        const { data } = await supabase.auth.getSession()
        session.value = data.session
        user.value = data.session?.user ?? null
        setSessionToken(data.session?.access_token ?? null)

        // Erzwungene Abmeldung nach 401: Store leeren, zum Login.
        register401SignOutCallback(() => {
          void signOut().finally(() => { void goToLogin() })
        })
      }
    }

    try {
      await loadWorkspaces()
    } catch {
      // Legacy (z.B. ohne Datenbank): Start nicht blockieren.
    }
    // Wiederhergestellte Session ohne aktiven Workspace (Liste nicht ladbar,
    // Bootstrap abgelehnt): nicht als angemeldet gelten lassen, sonst liefen
    // alle Anfragen ohne X-Agora-Workspace. Neu anmelden lädt erneut.
    if (session.value && !activeWorkspaceId.value) {
      await signOut()
    }
  }

  /** Router dynamisch laden (Zyklus store → router → store vermeiden). */
  async function goToLogin(): Promise<void> {
    try {
      const { default: router } = await import('../router')
      const current = router.currentRoute.value
      if (current.name === 'Login') return
      await router.push({ name: 'Login', query: { next: current.fullPath } })
    } catch {
      // Router nicht verfügbar (Tests) — nichts zu tun.
    }
  }

  function clearWorkspaceState(): void {
    workspaces.value = []
    activeWorkspaceId.value = null
    setActiveWorkspaceId(null)
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
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    if (data?.session) {
      session.value = data.session
      user.value = data.session.user ?? null
      setSessionToken(data.session.access_token)
    }
    // Erst mit gewähltem Workspace weiter: sonst fehlt Folgeanfragen der
    // Header X-Agora-Workspace (Bootstrap beim ersten Login). Ein Fehler
    // beim Laden lässt den Login scheitern; ein erneuter Versuch lädt neu.
    await loadWorkspaces()
    if (!activeWorkspaceId.value) throw new Error('workspace_unavailable')
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
    clearWorkspaceState()
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

  // Gleichzeitige Aufrufe (signIn und SIGNED_IN) teilen einen Lauf.
  let workspacesInFlight: Promise<void> | null = null
  function loadWorkspaces(): Promise<void> {
    if (!workspacesInFlight) {
      workspacesInFlight = fetchWorkspaces().finally(() => {
        workspacesInFlight = null
      })
    }
    return workspacesInFlight
  }

  /**
   * Liste laden, beim ersten Login mit Bootstrap, dann den Workspace wählen.
   * Fehler werden weitergereicht: signIn() darf ohne aktiven Workspace nicht
   * als erfolgreich gelten.
   */
  async function fetchWorkspaces(): Promise<void> {
    let list = await listWorkspaces()
    if (list.length === 0 && session.value) {
      list = [await bootstrapWorkspace()]
    }
    workspaces.value = list

    // Gespeicherten Workspace nehmen, solange er noch in der Liste steht.
    const persisted = _readPersistedWorkspaceId()
    const chosen = list.find((w) => w.workspace_id === persisted) ?? list[0] ?? null
    activeWorkspaceId.value = chosen?.workspace_id ?? null
    setActiveWorkspaceId(activeWorkspaceId.value)
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
    operatorAccess,
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
