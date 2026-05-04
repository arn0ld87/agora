/**
 * useActiveModelStore — Pinia-Store für den aktiven LLM-Modell-SSE-Stream.
 *
 * Slice E.2, Issue #213.
 *
 * Öffnet einen Signed-Ticket-SSE-Stream zu GET /api/llm/model-stream.
 * Das Ticket wird via POST /api/auth/ticket mit scope="llm-stream" geholt —
 * analog zu fetchStreamTicket in api/stream.ts, jedoch ohne sim-Suffix.
 *
 * Reconnect-Cap analog J.6 (LogDrawer): MAX_RECONNECT_ATTEMPTS = 5,
 * danach connectionStatus = 'failed'. reconnect() setzt zurück.
 *
 * isStale: true wenn seit dem letzten Frame mehr als STALE_AFTER_MS vergangen.
 * Ticking via setInterval (5 s) auf _now — sonst keine Reaktivität.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ModelActiveEvent } from '../contracts/modelActiveContract'
import { parseModelActiveEvent } from '../contracts/modelActiveContract'
import service, { getAgoraToken } from '../api/index'

const MAX_RECONNECT_ATTEMPTS = 5
export const STALE_AFTER_MS = 30_000
const TICK_INTERVAL_MS = 5_000

interface TicketApiResponse {
  data?: {
    ticket?: string
  }
}

async function fetchLlmStreamTicket(): Promise<string | undefined> {
  if (!getAgoraToken()) return undefined
  const res = await service.post('/api/auth/ticket', {
    scope: 'llm-stream',
    ttl_seconds: 60,
  })
  return (res as unknown as TicketApiResponse)?.data?.ticket
}

function buildLlmStreamUrl(ticket: string | undefined): string {
  const base = (import.meta as ImportMeta & { env: Record<string, string> }).env
    .VITE_API_BASE_URL ?? ''
  const path = `${base}/api/llm/model-stream`
  if (!ticket) return path
  return `${path}?ticket=${encodeURIComponent(ticket)}`
}

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'failed'

export const useActiveModelStore = defineStore('activeModel', () => {
  const lastEvent = ref<ModelActiveEvent | null>(null)
  const connectionStatus = ref<ConnectionStatus>('idle')
  const reconnectAttempts = ref(0)

  // Internal reactive clock — updated every TICK_INTERVAL_MS so isStale recomputes.
  const _now = ref(Date.now())
  let _tickTimer: ReturnType<typeof setInterval> | null = null
  let _es: EventSource | null = null

  const isStale = computed<boolean>(() => {
    if (lastEvent.value === null) return true
    return _now.value - lastEvent.value.ts * 1000 > STALE_AFTER_MS
  })

  function _closeEs(): void {
    if (_es) {
      _es.close()
      _es = null
    }
  }

  function _clearTick(): void {
    if (_tickTimer !== null) {
      clearInterval(_tickTimer)
      _tickTimer = null
    }
  }

  function _startTick(): void {
    _clearTick()
    _tickTimer = setInterval(() => {
      _now.value = Date.now()
    }, TICK_INTERVAL_MS)
  }

  async function connect(): Promise<void> {
    _closeEs()
    reconnectAttempts.value = 0
    connectionStatus.value = 'connecting'
    _startTick()

    let ticket: string | undefined
    try {
      ticket = await fetchLlmStreamTicket()
    } catch {
      connectionStatus.value = 'failed'
      _clearTick()
      return
    }

    // If the fetch returned 401-equivalent (no ticket despite token being set),
    // treat as failed.
    if (getAgoraToken() && !ticket) {
      connectionStatus.value = 'failed'
      _clearTick()
      return
    }

    const url = buildLlmStreamUrl(ticket)

    let es: EventSource
    try {
      es = new EventSource(url)
    } catch {
      connectionStatus.value = 'failed'
      _clearTick()
      return
    }
    _es = es

    es.onmessage = (ev: MessageEvent) => {
      // Successful frame resets reconnect counter.
      reconnectAttempts.value = 0
      if (connectionStatus.value !== 'open') {
        connectionStatus.value = 'open'
      }
      _now.value = Date.now()

      let raw: unknown
      try {
        raw = JSON.parse(ev.data as string)
      } catch {
        // Malformed frame — skip.
        return
      }

      const parsed = parseModelActiveEvent(raw)
      if (!parsed.ok) {
        console.warn('[useActiveModelStore] Zod parse failed', parsed.errors)
        return
      }
      lastEvent.value = parsed.data
    }

    es.onerror = () => {
      reconnectAttempts.value += 1
      if (reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS) {
        _closeEs()
        connectionStatus.value = 'failed'
        _clearTick()
        return
      }
      connectionStatus.value = 'reconnecting'
    }
  }

  function disconnect(): void {
    _closeEs()
    _clearTick()
    lastEvent.value = null
    reconnectAttempts.value = 0
    connectionStatus.value = 'idle'
  }

  async function reconnect(): Promise<void> {
    reconnectAttempts.value = 0
    await connect()
  }

  return {
    lastEvent,
    isStale,
    connectionStatus,
    reconnectAttempts,
    connect,
    disconnect,
    reconnect,
  }
})
