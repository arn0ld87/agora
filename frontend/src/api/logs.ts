// Issue #132 — Backend-Log-Viewer-API.
import api, { getAgoraToken } from './index'

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

export async function buildLogsStreamUrl(
  level: string | null = null,
  offset: number | null = null
): Promise<string> {
  // EventSource kann keine Custom-Header setzen — Auth läuft via signed
  // ticket (?ticket=…, scope "logs:stream"), analog zu buildSimulationStreamUrl.
  // Der offset sorgt dafür, dass der Stream genau dort weiterläuft wo
  // der Tail-Endpunkt aufgehört hat (verhindert Zeilen-Verlust, PR #146).
  const u = new URL('/api/logs/stream', window.location.origin)
  if (level) u.searchParams.set('level', level)
  if (Number.isInteger(offset) && offset !== null && offset >= 0) {
    u.searchParams.set('offset', String(offset))
  }
  if (!getAgoraToken()) return u.toString()
  try {
    const res = await api.post('/api/auth/ticket', { scope: 'logs:stream', ttl_seconds: 60 })
    const ticket = (res as unknown as { data?: { ticket?: string } })?.data?.ticket
    if (ticket) u.searchParams.set('ticket', ticket)
  } catch { /* open-mode or ticket-endpoint not reachable — proceed without ticket */ }
  return u.toString()
}
