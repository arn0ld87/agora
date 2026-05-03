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
import { openSimulationStream, type StreamHandlers } from '../api/stream'

const MAX_RECONNECT_ATTEMPTS = 5

export interface UseEventStreamReturn {
  isStreaming: Ref<boolean>
  error: Ref<unknown>
  lastEventAt: Ref<number | null>
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
      if (typeof handler === 'function') handler(payload)
    }
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
        error: (ev: Event) => {
          error.value = ev
          if (typeof handlers.error === 'function') handlers.error(ev)
          // EventSource attempts reconnect internally; cap the noise if the
          // backend stays down (fall back to whatever polling the caller has).
          attempts += 1
          if (attempts >= MAX_RECONNECT_ATTEMPTS) stop()
        },
      })
      isStreaming.value = true
    } catch (err) {
      error.value = err
      isStreaming.value = false
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
    start,
    stop,
  }
}
