import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { ApiError } from './envelope'
import { getSessionToken, getActiveWorkspaceId, setSessionToken } from '../auth/sessionState'

// Create axios instance
const service: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000, // 5 minute timeout (ontology generation may require longer time)
  headers: {
    'Content-Type': 'application/json'
  }
})

// Token-Quelle: localStorage (Dev-Default) oder Memory (Prod-Haertung).
// Memory-Mode aktiviert via VITE_AGORA_TOKEN_STORAGE=memory.
// In Memory-Mode lebt das Token nur im JS-Heap und ueberlebt keinen
// Page-Reload; das verhindert Persistence in localStorage (XSS-Residuum).
let _memoryToken = ''

export const setAgoraToken = (token: string | null | undefined): void => {
  if (import.meta.env.VITE_AGORA_TOKEN_STORAGE === 'memory') {
    _memoryToken = token || ''
    // Prevent residual localStorage token from shadowing the memory token.
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem('agora_token')
    }
  } else if (typeof window !== 'undefined') {
    if (token) {
      window.localStorage.setItem('agora_token', token)
    } else {
      window.localStorage.removeItem('agora_token')
    }
  }
}

export const getAgoraToken = (): string => {
  if (import.meta.env.VITE_AGORA_TOKEN_STORAGE === 'memory') {
    return _memoryToken || import.meta.env.VITE_AGORA_TOKEN || ''
  }
  // Dev-Fallback: localStorage (bewusst, siehe docs/auth.md)
  return (
    (typeof window !== 'undefined' && window.localStorage?.getItem('agora_token')) ||
    import.meta.env.VITE_AGORA_TOKEN ||
    ''
  )
}

/**
 * Returns the correct auth headers for the current authentication mode.
 *
 * - Supabase session present: `Authorization: Bearer <access_token>` and,
 *   if set, `X-Agora-Workspace`. Does NOT send `X-Agora-Token`.
 * - Legacy mode (no session): `X-Agora-Token` header if a token exists.
 * - No credentials: empty object.
 */
export function authHeaders(): Record<string, string> {
  const sessionToken = getSessionToken()
  if (sessionToken) {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${sessionToken}`,
    }
    const workspaceId = getActiveWorkspaceId()
    if (workspaceId) {
      headers['X-Agora-Workspace'] = workspaceId
    }
    return headers
  }
  // Legacy token mode
  const legacyToken = getAgoraToken()
  if (legacyToken) {
    return { 'X-Agora-Token': legacyToken }
  }
  return {}
}

/**
 * Returns true if there are any credentials available (legacy token or Supabase session).
 */
export function hasCredentials(): boolean {
  return !!(getSessionToken() || getAgoraToken())
}

// Request interceptor — hängt Auth-Header an, wenn einer bekannt ist.
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const headers = authHeaders()
    if (Object.keys(headers).length > 0) {
      config.headers = config.headers || {} as typeof config.headers
      for (const [key, value] of Object.entries(headers)) {
        config.headers[key] = value
      }
    }
    return config
  },
  (error: unknown) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 401-Retry-State: tracks which requests have already been retried to avoid infinite loops.
const _retried = new WeakSet<object>()

// Response interceptor (EPIC-09 Sub-Slice 5: surfaces ApiError with `code`).
// reason: interceptor intentionally returns response.data (the envelope body)
// instead of the full AxiosResponse; callers receive the unwrapped payload.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
service.interceptors.response.use(
  (response): any => {
    const res = response.data as Record<string, unknown> | null | undefined

    // 2xx mit `success: false` (Backend-eigene Fehlerlogik in 200er-Hülle)
    // → Code-tragenden ApiError werfen, damit UI semantisch reagieren kann.
    if (res && res['success'] === false) {
      const err = new ApiError({
        code: (res['code'] as string | undefined) || 'unknown_error',
        status: response.status || 0,
        message:
          (res['error'] as string | undefined) ||
          (res['message'] as string | undefined) ||
          'Unbekannter Fehler',
        details: res['details'] as Record<string, unknown> | undefined,
        originalResponse: res,
      })
      console.error('API Error:', err.code, '—', err.message)
      return Promise.reject(err)
    }

    return res
  },
  async (error: unknown) => {
    // 401 handling: wenn ein Supabase-Session-Token vorhanden ist und der
    // Request noch nicht retryed wurde, einmal refreshSession + retry.
    const axiosError = error as {
      response?: { data?: Record<string, unknown>; status?: number }
      config?: object
      code?: string
      message?: string
    }

    if (
      axiosError?.response?.status === 401 &&
      getSessionToken() &&
      axiosError.config &&
      !_retried.has(axiosError.config)
    ) {
      _retried.add(axiosError.config)
      try {
        // Lazy-import to avoid circular dependency at module load time
        const { getSupabaseClient } = await import('../auth/supabaseClient')
        const supabase = getSupabaseClient()
        if (supabase) {
          const { data: refreshed, error: refreshError } = await supabase.auth.refreshSession()
          if (!refreshError && refreshed?.session?.access_token) {
            // Neuen Token sofort setzen, nicht auf onAuthStateChange warten;
            // der Request-Interceptor hängt ihn beim Retry an.
            setSessionToken(refreshed.session.access_token)
            return service.request(axiosError.config as Parameters<typeof service.request>[0])
          }
        }
      } catch {
        // Refresh failed — fall through to signOut
      }
      // Refresh failed: Token verwerfen, signOut und zum Login.
      setSessionToken(null)
      try {
        const { getSupabaseClient } = await import('../auth/supabaseClient')
        const supabase = getSupabaseClient()
        if (supabase) {
          await supabase.auth.signOut()
        }
      } catch { /* ignore */ }
      // Notify the auth store via callback if registered
      if (_on401SignOut) {
        _on401SignOut()
      }
    }

    // Achshalsbruch oder 4xx/5xx-Pfad: Backend-Envelope auspacken, falls da.
    const data = axiosError?.response?.data
    if (data && data['success'] === false) {
      const err = new ApiError({
        code: (data['code'] as string | undefined) || 'unknown_error',
        status: axiosError.response?.status || 0,
        message:
          (data['error'] as string | undefined) ||
          (data['message'] as string | undefined) ||
          'Unbekannter Fehler',
        details: data['details'] as Record<string, unknown> | undefined,
        originalResponse: data,
      })
      console.error('Backend error:', err.code, '—', err.message)
      return Promise.reject(err)
    }

    // Kein Envelope verfügbar (z.B. Network Error, Timeout): heuristischer Code.
    let code = 'unknown_error'
    let message = (axiosError as { message?: string }).message || 'Unbekannter Fehler'
    if (axiosError.code === 'ECONNABORTED' || (axiosError as { message?: string }).message?.includes('timeout')) {
      code = 'timeout'
      message = 'Zeitüberschreitung — Backend antwortet zu langsam'
    } else if ((axiosError as { message?: string }).message === 'Network Error') {
      code = 'service_unavailable'
      message = 'Backend offline oder nicht erreichbar'
    }
    const wrapped = new ApiError({
      code,
      status: axiosError.response?.status || 0,
      message,
      originalResponse: error,
    })
    console.error('Network/transport error:', wrapped.code, '—', wrapped.message)
    return Promise.reject(wrapped)
  }
)

// Callback registered by the auth store for 401-triggered signOut+redirect.
let _on401SignOut: (() => void) | null = null

export function register401SignOutCallback(cb: () => void): void {
  _on401SignOut = cb
}

// Retry-Klassifizierung: nur transport-/server-seitige Fehler sind retry-tauglich.
// 4xx-Client-Errors (Validation, Auth) wiederholen sich nicht — retry liefert
// dasselbe Ergebnis und kann bei non-idempotenten POSTs doppelt-create
// auslösen. Network/Timeout/5xx werden retryt; alles andere bubbled sofort.
function _isRetryableError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const e = error as { code?: string; status?: number; response?: { status?: number } }
  if (e.code === 'timeout' || e.code === 'service_unavailable') return true
  const status = e.status ?? e.response?.status ?? 0
  return status >= 500 && status < 600
}

/**
 * Wiederholt `requestFn` bei retry-fähigen Transport-/Server-Fehlern
 * (Timeout, Network, 5xx). Client-Fehler (4xx) bubbeln sofort, damit
 * non-idempotente POSTs nicht doppelt ausgeführt werden.
 */
export const requestWithRetry = async <T>(
  requestFn: () => Promise<T>,
  maxRetries = 3,
  delay = 1000
): Promise<T> => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      const isLast = i === maxRetries - 1
      if (isLast || !_isRetryableError(error)) throw error

      console.warn(`Request failed (retryable), retrying (${i + 1}/${maxRetries})...`)
      await new Promise<void>(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
  // Unreachable: loop always throws on last iteration; TS needs this.
  throw new Error('requestWithRetry: exhausted retries')
}

export default service
