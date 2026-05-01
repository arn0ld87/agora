// Issue #132 — Backend-Log-Viewer-API.
import api from './index'

export function fetchLogs({ tail = 200, level = null } = {}) {
  const params = { tail }
  if (level) params.level = level
  return api.get('/api/logs', { params })
}

export function logsStreamUrl(token, level = null, offset = null) {
  // EventSource kann keine Header setzen → Token via ?token=. SSE-Pfad
  // entspricht den anderen Stream-Endpoints (vgl. simulation_stream).
  // ``offset`` wird vom Tail-Endpunkt geliefert und sorgt dafür, dass
  // der Stream genau dort weiterläuft — ohne ihn gehen Log-Zeilen
  // verloren, die zwischen Tail-Antwort und Stream-Connect geschrieben
  // werden (PR #146-Review).
  const u = new URL('/api/logs/stream', window.location.origin)
  if (token) u.searchParams.set('token', token)
  if (level) u.searchParams.set('level', level)
  if (Number.isInteger(offset) && offset >= 0) {
    u.searchParams.set('offset', String(offset))
  }
  return u.toString()
}
