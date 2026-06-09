/**
 * useSimClock — Layer-0 Sim-Zeit-Composable (Task 1).
 *
 * Konsumiert PostCreatedEvent.sim_time (ISO-8601, tz-aware, optional).
 * Singleton pro simulationId — wie useSimFeed.
 *
 * Responsibilities:
 * - `start`: erster gesehener sim_time → Anker
 * - `currentSimTime`: letzter Wert (monoton; ignoriert kleinere Werte)
 * - `elapsed`: Sekunden seit `start`, leicht extrapoliert via setInterval(1 s)
 * - `ingest(post)`: vom SSE-Handler aufgerufen
 * - `stop()`: gibt Interval frei (z. B. on simulationId-Wechsel)
 *
 * Bewusst NICHT abhängig von der Sim-Rate — ein ruhiger 1-Hz-Tick reicht für
 * UI-Anzeige; präzise Werte landen mit jedem post_created-Frame.
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

export interface UseSimClockReturn {
  currentSimTime: Ref<Date | null>
  start: Ref<Date | null>
  elapsed: ComputedRef<number>
  ingest: (post: PostCreatedEvent) => void
  stop: () => void
}

interface ClockState {
  api: UseSimClockReturn
  refCount: number
}

const stores = new Map<string, ClockState>()
const MAX_STORES = 10

function createClock(): UseSimClockReturn {
  const currentSimTime = ref<Date | null>(null)
  const start = ref<Date | null>(null)
  // Wallclock-Anker: wann ist `currentSimTime` zuletzt aus einem echten
  // Frame gesetzt worden? Für die 1-Hz-Extrapolation.
  let lastWallReceivedAt: number | null = null
  // ticker-tick-Ref nur damit `elapsed` reaktiv ist; der Wert selbst ist egal.
  const tick = ref(0)
  let intervalId: ReturnType<typeof setInterval> | null = null

  function ensureInterval(): void {
    if (intervalId !== null) return
    intervalId = setInterval(() => {
      tick.value = (tick.value + 1) % 1_000_000
    }, 1_000)
  }

  function ingest(post: PostCreatedEvent): void {
    const iso = post?.sim_time
    if (!iso) return
    const parsed = new Date(iso)
    if (Number.isNaN(parsed.getTime())) return
    if (start.value === null) {
      start.value = parsed
    }
    // Monotonie: kleinere Werte ignorieren (out-of-order SSE-Frames).
    if (currentSimTime.value !== null && parsed.getTime() < currentSimTime.value.getTime()) {
      return
    }
    currentSimTime.value = parsed
    lastWallReceivedAt = Date.now()
    ensureInterval()
  }

  const elapsed = computed<number>(() => {
    // Touch tick so the computed re-runs every second.
    void tick.value
    if (start.value === null || currentSimTime.value === null) return 0
    const baseSec = (currentSimTime.value.getTime() - start.value.getTime()) / 1000
    const forecast = lastWallReceivedAt !== null
      ? Math.max(0, (Date.now() - lastWallReceivedAt) / 1000)
      : 0
    return baseSec + forecast
  })

  function stop(): void {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
    currentSimTime.value = null
    start.value = null
    lastWallReceivedAt = null
    tick.value = 0
  }

  return { currentSimTime, start, elapsed, ingest, stop }
}

export function useSimClock(simulationId: string): UseSimClockReturn {
  let state = stores.get(simulationId)
  if (!state) {
    if (stores.size >= MAX_STORES) {
      const oldestKey = stores.keys().next().value
      if (oldestKey !== undefined) {
        const old = stores.get(oldestKey)
        old?.api.stop()
        stores.delete(oldestKey)
      }
    }
    state = { api: createClock(), refCount: 0 }
    stores.set(simulationId, state)
  }
  state.refCount += 1
  return state.api
}

export function clearSimClock(simulationId: string): void {
  const state = stores.get(simulationId)
  if (!state) return
  state.api.stop()
  stores.delete(simulationId)
}
