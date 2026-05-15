// Lightweight EventSource factory for Agora SSE endpoints (Issue #9 Phase C).
// EventSource cannot set custom headers, so URL-bound auth ships as a
// short-lived signed ticket via `?ticket=...` (P0.2c). The bearer is fetched
// once via POST /api/auth/ticket and the resulting ticket is scope-bound to
// `sse:<simulationId>`, valid for ~60s and reusable inside that window so
// EventSource auto-reconnects keep working.

import { getAgoraToken } from './index'
import { useApiAuth } from '../composables/useApiAuth'
import { PostCreatedEventSchema, type PostCreatedEvent } from '../contracts/postEventContract'

// --- SSE event types (derived from backend/app/api/simulation_stream.py) ---
//
// event: hello        — sent once on connect: { simulation_id, ts }
// event: ping         — heartbeat every ~15 s: { ts }
// event: state        — run-state snapshot: { type, simulation_id, payload, ts }
// event: control      — pause/stop flags:   { type, simulation_id, payload, ts }
// event: post_created — live post from OASIS runner (Slice 5-pre):
//                       PostCreatedEvent payload

export interface SseHelloPayload {
  simulation_id: string
  ts: number
}

export interface SsePingPayload {
  ts: number
}

export interface SseEventFrame {
  type: string
  simulation_id: string
  payload: Record<string, unknown>
  ts: string | null
  /** W3C hex trace_id injected by the backend SSE stream (Slice 1e). Optional — absent when OTEL_ENABLED=false. */
  trace_id?: string
}

/** Re-export for consumers that want the fully typed PostCreatedEvent. */
export type { PostCreatedEvent }

/** Handler map for `openSimulationStream`. Each handler receives the already-parsed payload. */
export interface StreamHandlers {
  state?: (event: SseEventFrame) => void
  control?: (event: SseEventFrame) => void
  hello?: (event: SseHelloPayload) => void
  ping?: (event: SsePingPayload) => void
  /** Slice 5-pre: live post from OASIS runner, Zod-parsed PostCreatedEvent. */
  post_created?: (event: PostCreatedEvent) => void
  error?: (event: Event) => void
}

export async function fetchStreamTicket(
  simulationId: string,
  { ttlSeconds = 60 }: { ttlSeconds?: number } = {}
): Promise<string | undefined> {
  if (!simulationId) throw new Error('simulationId is required')
  // Delegiert an useApiAuth.fetchTicket für Cache + Auto-Refresh-Support.
  // ttlSeconds wird durchgereicht (Copilot-Followup PR #466).
  return useApiAuth.fetchTicket(`sse:${simulationId}`, ttlSeconds)
}

export async function buildSimulationStreamUrl(simulationId: string): Promise<string> {
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
export async function openSimulationStream(
  simulationId: string,
  handlers: StreamHandlers = {}
): Promise<EventSource> {
  const url = await buildSimulationStreamUrl(simulationId)
  const source = new EventSource(url)

  const namedEvents = ['state', 'control', 'hello', 'ping'] as const
  for (const name of namedEvents) {
    const handler = handlers[name]
    if (typeof handler === 'function') {
      source.addEventListener(name, (ev: MessageEvent) => {
        try {
          // reason: loop over const tuple; each handler is typed per key but
          // TypeScript cannot narrow through the dynamic key — cast is safe.
          ;(handler as (payload: unknown) => void)(JSON.parse(ev.data as string))
        } catch (err) {
          // Malformed SSE frame — swallow but let debug listeners see it.
          console.warn(`[stream] dropped malformed ${name} event`, err)
        }
      })
    }
  }

  // Slice 5-pre: post_created is Zod-parsed for type safety.
  if (typeof handlers.post_created === 'function') {
    const postHandler = handlers.post_created
    source.addEventListener('post_created', (ev: MessageEvent) => {
      try {
        const raw = JSON.parse(ev.data as string)
        // Backend wraps in SimulationEvent envelope: { type, simulation_id, payload, ts }
        const payload = raw?.payload ?? raw
        const parsed = PostCreatedEventSchema.safeParse(payload)
        if (!parsed.success) {
          console.warn('[stream] post_created Zod parse failed', parsed.error)
          return
        }
        postHandler(parsed.data)
      } catch (err) {
        console.warn('[stream] dropped malformed post_created event', err)
      }
    })
  }

  if (typeof handlers.error === 'function') {
    source.onerror = handlers.error
  }

  return source
}
