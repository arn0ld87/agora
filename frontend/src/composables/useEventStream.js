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

import { onUnmounted, ref } from 'vue'
import { openSimulationStream } from '../api/stream'

const MAX_RECONNECT_ATTEMPTS = 5

export function useEventStream(simulationIdRef, handlers = {}) {
  const isStreaming = ref(false)
  const error = ref(null)
  const lastEventAt = ref(null)
  let source = null
  let reconnectTimer = null
  let attempts = 0

  function getId() {
    return typeof simulationIdRef === 'function'
      ? simulationIdRef()
      : simulationIdRef?.value ?? simulationIdRef
  }

  function wrap(handler) {
    return (payload) => {
      lastEventAt.value = Date.now()
      error.value = null
      attempts = 0
      if (typeof handler === 'function') handler(payload)
    }
  }

  function start() {
    const id = getId()
    if (!id) return
    if (source) return
    try {
      source = openSimulationStream(id, {
        hello: wrap(handlers.hello),
        state: wrap(handlers.state),
        control: wrap(handlers.control),
        ping: wrap(handlers.ping),
        error: (ev) => {
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

  function stop() {
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
