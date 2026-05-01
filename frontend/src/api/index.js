import axios from 'axios'
import { ApiError } from './envelope'

// Create axios instance
const service = axios.create({
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

export const setAgoraToken = (token) => {
  if (import.meta.env.VITE_AGORA_TOKEN_STORAGE === 'memory') {
    _memoryToken = token || ''
  } else if (typeof window !== 'undefined') {
    if (token) {
      window.localStorage.setItem('agora_token', token)
    } else {
      window.localStorage.removeItem('agora_token')
    }
  }
}

export const getAgoraToken = () => {
  if (import.meta.env.VITE_AGORA_TOKEN_STORAGE === 'memory') {
    return _memoryToken || import.meta.env.VITE_AGORA_TOKEN || ''
  }
  // Dev-Fallback: localStorage (bewusst, siehe docu/auth.md)
  return (
    (typeof window !== 'undefined' && window.localStorage?.getItem('agora_token')) ||
    import.meta.env.VITE_AGORA_TOKEN ||
    ''
  )
}

// Request interceptor — hängt Token-Header an, wenn einer bekannt ist.
service.interceptors.request.use(
  config => {
    const token = getAgoraToken()
    if (token) {
      config.headers = config.headers || {}
      config.headers['X-Agora-Token'] = token
    }
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor (EPIC-09 Sub-Slice 5: surfaces ApiError with `code`).
service.interceptors.response.use(
  response => {
    const res = response.data

    // 2xx mit `success: false` (Backend-eigene Fehlerlogik in 200er-Hülle)
    // → Code-tragenden ApiError werfen, damit UI semantisch reagieren kann.
    if (res && res.success === false) {
      const err = new ApiError({
        code: res.code || 'unknown_error',
        status: response.status || 0,
        message: res.error || res.message || 'Unbekannter Fehler',
        details: res.details,
        originalResponse: res,
      })
      console.error('API Error:', err.code, '—', err.message)
      return Promise.reject(err)
    }

    return res
  },
  error => {
    // Achshalsbruch oder 4xx/5xx-Pfad: Backend-Envelope auspacken, falls da.
    const data = error?.response?.data
    if (data && data.success === false) {
      const err = new ApiError({
        code: data.code || 'unknown_error',
        status: error.response?.status || 0,
        message: data.error || data.message || 'Unbekannter Fehler',
        details: data.details,
        originalResponse: data,
      })
      console.error('Backend error:', err.code, '—', err.message)
      return Promise.reject(err)
    }

    // Kein Envelope verfügbar (z.B. Network Error, Timeout): heuristischer Code.
    let code = 'unknown_error'
    let message = error.message || 'Unbekannter Fehler'
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      code = 'timeout'
      message = 'Zeitüberschreitung — Backend antwortet zu langsam'
    } else if (error.message === 'Network Error') {
      code = 'service_unavailable'
      message = 'Backend offline oder nicht erreichbar'
    }
    const wrapped = new ApiError({
      code,
      status: error.response?.status || 0,
      message,
      originalResponse: error,
    })
    console.error('Network/transport error:', wrapped.code, '—', wrapped.message)
    return Promise.reject(wrapped)
  }
)

// Request function with retry
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error

      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
