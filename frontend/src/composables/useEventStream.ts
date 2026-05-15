// SSE-backed sibling of usePolling (Issue #9 Phase C).
//
// Same public shape as usePolling ({ data, error, isStreaming, start, stop }),
// but driven by an EventSource and a backend bus-bridge at
// /api/simulation/<id>/stream instead of periodic HTTP polls.
//
// Reconnect: EventSource reconnects automatically on network hiccups. If the
// server closes the stream we surface the error and stop — the caller can
// decide to retry. A simple exponential backoff kicks in after repeated
// failures so we don't hammer a misbehaving backend.

import { onUnmounted, ref, type Ref } from 'vue'
import { context, propagation } from '@opentelemetry/api'
import {
  openSimulationStream,
  type StreamHandlers,
  type SseEventFrame,
  type PostCreatedEvent,
} from '../api/stream'
import { getTracer } from '../observability/tracing'

const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_BASE_DELAY_MS = 500
const RECONNECT_MAX_DELAY_MS = 8000

export interface UseEventStreamReturn {
  isStreaming: Ref<boolean>
  error: Ref<unknown>
  lastEventAt: Ref<number | null>
  lastTraceId: Ref<string | null>
  start: () => Promise<void>
  stop: () => void
}

export function useEventStream(
  simulationIdRef: Ref<string> | (() => string) | string,
  handlers: StreamHandlers = {}
): UseEventStreamReturn {
  const isStreaming = ref(false)
  const error = ref<unknown>(null)
  const lastEventAt = ref<number | null>(null)
  const lastTraceId = ref<string | null>(null)
  let source: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let attempts = 0

  function getId(): string {
    if (typeof simulationIdRef === 'function') return simulationIdRef()
    if (simulationIdRef !== null && typeof simulationIdRef === 'object' && 'value' in simulationIdRef) {
      return (simulationIdRef as Ref<string>).value
    }
    return simulationIdRef as string
  }

  function wrap<T>(handler: ((payload: T) => void) | undefined): (payload: T) => void {
    return (payload: T) => {
      lastEventAt.value = Date.now()
      error.value = null
      attempts = 0
      // Slice 1e: capture trace_id from SSE event frames (state/control).
      // Guard via 'in' so hello/ping payloads (no trace_id field) are ignored.
      if (payload !== null && typeof payload === 'object' && 'trace_id' in payload) {
        // Double-cast through unknown: T is generic and TS cannot prove overlap
        // with SseEventFrame directly; the 'in' guard ensures shape is correct.
        const frame = payload as unknown as SseEventFrame
        if (frame.trace_id) {
          lastTraceId.value = frame.trace_id
          // Short browser span for SSE event correlation — no-op when OTEL disabled.
          // Extract parent context from synthetic W3C traceparent so the browser
          // span hangs off the backend trace instead of becoming a new root.
          // Span-ID `1` is a placeholder since the SSE-Frame carries only the
          // trace-ID — that's enough for SigNoz to group the spans under one trace.
          const traceparent = `00-${frame.trace_id}-0000000000000001-01`
          const parentContext = propagation.extract(context.active(), { traceparent })
          const tracer = getTracer()
          const span = tracer.startSpan(
            `agora.sse.event.${frame.type}`,
            {
              attributes: {
                'agora.simulation.id': frame.simulation_id,
                'agora.event.trace_id': frame.trace_id,
              },
            },
            parentContext,
          )
          span.end()
        }
      }
      if (typeof handler === 'function') handler(payload)
    }
  }

  function scheduleReconnect(): void {
    if (reconnectTimer) return  // bereits geplant
    if (attempts >= MAX_RECONNECT_ATTEMPTS) {
      stop()
      return
    }
    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * 2 ** (attempts - 1),
      RECONNECT_MAX_DELAY_MS,
    )
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      // Alte Source ist geschlossen — neuer Versuch mit frischem Ticket.
      void start()
    }, delay)
  }

  async function start(): Promise<void> {
    const id = getId()
    if (!id) return
    if (source) return
    try {
      // openSimulationStream is async since P0.2c — it fetches a signed ticket
      // before opening the EventSource. Errors during ticket fetch surface
      // here just like the previous synchronous failures.
      source = await openSimulationStream(id, {
        hello: wrap(handlers.hello),
        state: wrap(handlers.state),
        control: wrap(handlers.control),
        ping: wrap(handlers.ping),
        // Slice 5-pre: post_created is already Zod-parsed by openSimulationStream;
        // wrap() handles lastEventAt + error-reset bookkeeping.
        post_created: handlers.post_created
          ? (wrap as unknown as (h: (p: PostCreatedEvent) => void) => (p: PostCreatedEvent) => void)(handlers.post_created)
          : undefined,
        error: (ev: Event) => {
          error.value = ev
          if (typeof handlers.error === 'function') handlers.error(ev)
          // Smoke-Live 2026-05-15: EventSource interner Reconnect nutzt das
          // ALTE Ticket-URL, das nach 60 s TTL abläuft → Endlos-Loop.
          // Wir schließen die Source aktiv, holen mit Backoff ein frisches
          // Ticket über ``openSimulationStream``.
          attempts += 1
          if (source) {
            source.close()
            source = null
          }
          isStreaming.value = false
          scheduleReconnect()
        },
      })
      isStreaming.value = true
    } catch (err) {
      error.value = err
      isStreaming.value = false
      attempts += 1
      scheduleReconnect()
    }
  }

  function stop(): void {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (source) {
      source.close()
      source = null
    }
    isStreaming.value = false
  }

  onUnmounted(stop)

  return {
    isStreaming,
    error,
    lastEventAt,
    lastTraceId,
    start,
    stop,
  }
}
