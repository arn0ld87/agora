/**
 * useActiveModelStore — Pinia-Store für den aktiven LLM-Modell-SSE-Stream.
 *
 * Slice E.2 / Observability Wave 2026-05 (Anti-Flicker, Issue #213).
 *
 * Reconnect-Verhalten:
 * - Reconnects sind unbegrenzt (kein hartes Limit).
 * - connectionStatus wechselt erst nach RECONNECTING_AFTER_MS (30 s) ohne
 *   erfolgreichen Frame auf 'reconnecting' — kurze Backend-Hiccups bleiben
 *   stillen, analog LogDrawer Slice 4.
 * - currentModel / lastKnownModel werden beim onerror NICHT geleert, so dass
 *   die Badge weiterhin den letzten bekannten Modell-String zeigt.
 *
 * Fehlerzustand 'failed':
 * - Wird gesetzt wenn der Ticket-Fetch fehlschlägt oder EventSource-Konstruktor
 *   wirft. Reload-Button im Badge ermöglicht manuelles reconnect().
 *
 * isStale: true wenn seit dem letzten Frame mehr als STALE_AFTER_MS vergangen.
 * Ticking via setInterval (5 s) auf _now — sonst keine Reaktivität.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ModelActiveEvent } from '../contracts/modelActiveContract'
import { parseModelActiveEvent } from '../contracts/modelActiveContract'
import { getAgoraToken } from '../api/index'
import { useApiAuth } from '../composables/useApiAuth'

export const STALE_AFTER_MS = 30_000
export const RECONNECTING_AFTER_MS = 30_000
const TICK_INTERVAL_MS = 5_000

async function fetchLlmStreamTicket(): Promise<string | undefined> {
  if (!getAgoraToken()) return undefined
  return useApiAuth.fetchTicket('llm-stream')
}

function buildLlmStreamUrl(ticket: string | undefined): string {
  const base = (import.meta as ImportMeta & { env: Record<string, string> }).env
    .VITE_API_BASE_URL ?? ''
  const path = `${base}/api/llm/model-stream`
  if (!ticket) return path
  return `${path}?ticket=${encodeURIComponent(ticket)}`
}

export type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed'

export const useActiveModelStore = defineStore('activeModel', () => {
  const lastEvent = ref<ModelActiveEvent | null>(null)
  const connectionStatus = ref<ConnectionStatus>('idle')
  const reconnectAttempts = ref(0)

  /**
   * lastKnownModel: letzter erfolgreicher Modell-String innerhalb der
   * Browser-Tab-Session. Wird nie gelöscht, solange das Tab lebt.
   */
  const lastKnownModel = ref<string | null>(null)

  // Internal reactive clock — updated every TICK_INTERVAL_MS so isStale recomputes.
  const _now = ref(Date.now())
  let _tickTimer: ReturnType<typeof setInterval> | null = null
  let _es: EventSource | null = null

  /**
   * _reconnectingTimer: Delayed transition 'connecting' → 'reconnecting'.
   * Gesetzt beim ersten onerror, gelöscht beim nächsten erfolgreichen Frame.
   */
  let _reconnectingTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * currentModel: Modell-String aus dem letzten validen Frame.
   * Wird beim onerror NICHT auf null gesetzt.
   */
  const currentModel = computed<string | null>(() =>
    lastEvent.value?.model ?? null,
  )

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

  function _clearReconnectingTimer(): void {
    if (_reconnectingTimer !== null) {
      clearTimeout(_reconnectingTimer)
      _reconnectingTimer = null
    }
  }

  /**
   * Startet den 30-s-Countdown nach dem onerror.
   * Nach Ablauf: Status auf 'reconnecting', wenn bis dahin kein Frame kam.
   */
  function _scheduleReconnecting(): void {
    _clearReconnectingTimer()
    _reconnectingTimer = setTimeout(() => {
      _reconnectingTimer = null
      // Only flip to reconnecting if still not connected.
      if (connectionStatus.value !== 'connected' && connectionStatus.value !== 'failed') {
        connectionStatus.value = 'reconnecting'
      }
    }, RECONNECTING_AFTER_MS)
  }

  async function connect(): Promise<void> {
    _closeEs()
    _clearReconnectingTimer()
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
      // Successful frame: reset reconnect counter, clear pending reconnecting timer.
      reconnectAttempts.value = 0
      _clearReconnectingTimer()
      if (connectionStatus.value !== 'connected') {
        connectionStatus.value = 'connected'
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
      // Persist last known model for the tab lifetime.
      lastKnownModel.value = parsed.data.model
    }

    es.onerror = () => {
      reconnectAttempts.value += 1
      // Do NOT clear lastEvent or lastKnownModel — Badge should keep showing
      // the last known model string during reconnect.
      // Only schedule 'reconnecting' flip after the grace period.
      _scheduleReconnecting()
    }
  }

  function disconnect(): void {
    _closeEs()
    _clearTick()
    _clearReconnectingTimer()
    lastEvent.value = null
    // lastKnownModel is intentionally NOT cleared — persists within tab session.
    reconnectAttempts.value = 0
    connectionStatus.value = 'idle'
  }

  async function reconnect(): Promise<void> {
    reconnectAttempts.value = 0
    await connect()
  }

  return {
    lastEvent,
    lastKnownModel,
    currentModel,
    isStale,
    connectionStatus,
    reconnectAttempts,
    connect,
    disconnect,
    reconnect,
  }
})
