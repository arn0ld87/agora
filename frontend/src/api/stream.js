// Lightweight EventSource factory for Agora SSE endpoints (Issue #9 Phase C).
// EventSource cannot set custom headers, so URL-bound auth ships as a
// short-lived signed ticket via `?ticket=...` (P0.2c). The bearer is fetched
// once via POST /api/auth/ticket and the resulting ticket is scope-bound to
// `sse:<simulationId>`, valid for ~60s and reusable inside that window so
// EventSource auto-reconnects keep working.

import service, { getAgoraToken } from './index'

export async function fetchStreamTicket(simulationId, { ttlSeconds = 60 } = {}) {
  if (!simulationId) throw new Error('simulationId is required')
  const res = await service.post('/api/auth/ticket', {
    scope: `sse:${simulationId}`,
    ttl_seconds: ttlSeconds,
  })
  // service interceptor unwraps to { success, data }
  return res?.data?.ticket
}

export async function buildSimulationStreamUrl(simulationId) {
  if (!simulationId) throw new Error('simulationId is required')
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const path = `${base}/api/simulation/${encodeURIComponent(simulationId)}/stream`
  // Without a bearer (open-mode backend) we don't need a ticket either.
  if (!getAgoraToken()) return path
  const ticket = await fetchStreamTicket(simulationId)
  return ticket ? `${path}?ticket=${encodeURIComponent(ticket)}` : path
}

/**
 * Open an EventSource for the given simulation and wire event handlers.
 * Returns a Promise resolving to the raw EventSource so callers can call
 * `.close()` when unmounting.
 *
 * Handlers map: { state?: fn, control?: fn, hello?: fn, ping?: fn, error?: fn }
 */
export async function openSimulationStream(simulationId, handlers = {}) {
  const url = await buildSimulationStreamUrl(simulationId)
  const source = new EventSource(url)

  for (const name of ['state', 'control', 'hello', 'ping']) {
    if (typeof handlers[name] === 'function') {
      source.addEventListener(name, (ev) => {
        try {
          handlers[name](JSON.parse(ev.data))
        } catch (err) {
          // Malformed SSE frame — swallow but let debug listeners see it.
          console.warn(`[stream] dropped malformed ${name} event`, err)
        }
      })
    }
  }

  if (typeof handlers.error === 'function') {
    source.onerror = handlers.error
  }

  return source
}
