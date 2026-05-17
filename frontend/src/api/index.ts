import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { ApiError } from './envelope'

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

// Request interceptor — hängt Token-Header an, wenn einer bekannt ist.
service.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAgoraToken()
    if (token) {
      config.headers = config.headers || {} as typeof config.headers
      config.headers['X-Agora-Token'] = token
    }
    return config
  },
  (error: unknown) => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

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
  (error: unknown) => {
    // Achshalsbruch oder 4xx/5xx-Pfad: Backend-Envelope auspacken, falls da.
    const axiosError = error as {
      response?: { data?: Record<string, unknown>; status?: number }
      code?: string
      message?: string
    }
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
    let message = axiosError.message || 'Unbekannter Fehler'
    if (axiosError.code === 'ECONNABORTED' || axiosError.message?.includes('timeout')) {
      code = 'timeout'
      message = 'Zeitüberschreitung — Backend antwortet zu langsam'
    } else if (axiosError.message === 'Network Error') {
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
