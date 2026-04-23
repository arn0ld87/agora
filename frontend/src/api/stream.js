// Lightweight EventSource factory for Agora SSE endpoints (Issue #9 Phase C).
// EventSource cannot set custom headers, so the Agora token — if present —
// goes in a `?token=...` query param. The backend auth guard already honours
// that fallback (see backend/app/utils/auth.py::_extract_token).

import { getAgoraToken } from './index'

export function buildSimulationStreamUrl(simulationId) {
  if (!simulationId) throw new Error('simulationId is required')
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const path = `${base}/api/simulation/${encodeURIComponent(simulationId)}/stream`
  const token = getAgoraToken()
  return token ? `${path}?token=${encodeURIComponent(token)}` : path
}

/**
 * Open an EventSource for the given simulation and wire event handlers.
 * Returns the raw EventSource so callers can call `.close()` when unmounting.
 *
 * Handlers map: { state?: fn, control?: fn, hello?: fn, ping?: fn, error?: fn }
 */
export function openSimulationStream(simulationId, handlers = {}) {
  const source = new EventSource(buildSimulationStreamUrl(simulationId))

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
