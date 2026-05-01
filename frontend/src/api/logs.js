// Issue #132 — Backend-Log-Viewer-API.
import api from './index'

export function fetchLogs({ tail = 200, level = null } = {}) {
  const params = { tail }
  if (level) params.level = level
  return api.get('/api/logs', { params })
}

export function logsStreamUrl(token, level = null) {
  // EventSource kann keine Header setzen → Token via ?token=. SSE-Pfad
  // entspricht den anderen Stream-Endpoints (vgl. simulation_stream).
  const u = new URL('/api/logs/stream', window.location.origin)
  if (token) u.searchParams.set('token', token)
  if (level) u.searchParams.set('level', level)
  return u.toString()
}
