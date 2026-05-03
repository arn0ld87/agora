// Issue #132 — Backend-Log-Viewer-API.
import api from './index'

export interface FetchLogsParams {
  tail?: number
  level?: string | null
}

export interface LogEntry {
  ts: string
  level: string
  logger: string
  message: string
  offset?: number
}

export interface FetchLogsResponse {
  lines: LogEntry[]
  offset: number
  total: number
}

export function fetchLogs({ tail = 200, level = null }: FetchLogsParams = {}): Promise<FetchLogsResponse> {
  const params: Record<string, unknown> = { tail }
  if (level) params['level'] = level
  return api.get('/api/logs', { params })
}

export function logsStreamUrl(
  token: string | null | undefined,
  level: string | null = null,
  offset: number | null = null
): string {
  // EventSource kann keine Header setzen → Token via ?token=. SSE-Pfad
  // entspricht den anderen Stream-Endpoints (vgl. simulation_stream).
  // ``offset`` wird vom Tail-Endpunkt geliefert und sorgt dafür, dass
  // der Stream genau dort weiterläuft — ohne ihn gehen Log-Zeilen
  // verloren, die zwischen Tail-Antwort und Stream-Connect geschrieben
  // werden (PR #146-Review).
  const u = new URL('/api/logs/stream', window.location.origin)
  if (token) u.searchParams.set('token', token)
  if (level) u.searchParams.set('level', level)
  if (Number.isInteger(offset) && offset !== null && offset >= 0) {
    u.searchParams.set('offset', String(offset))
  }
  return u.toString()
}
