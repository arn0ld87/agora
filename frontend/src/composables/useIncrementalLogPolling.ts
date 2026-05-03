/**
 * useIncrementalLogPolling — inkrementelles Log-Polling über `usePolling`.
 *
 * Issue #39 (EPIC-05-ST-03): konsolidiert die duplizierte Append- und
 * Auto-Scroll-Logik aus `Step3Simulation.vue` (Simulation Console Logs)
 * sowie `Step4Report.vue` (Agent Logs + Console Logs). Die drei Stellen
 * teilen exakt dasselbe Muster:
 *
 *   1. Cursor `since_line` als Ref.
 *   2. `lines`-Array als Ref.
 *   3. `fetcher(sinceLine)` liefert `{ lines, next_line, total_lines }`.
 *   4. Neue Lines werden geparst (oder roh übernommen) und an `lines` gehängt.
 *   5. Cursor wird auf `next_line ?? total_lines` gesetzt.
 *   6. Nach jedem Append wird der Container ans untere Ende gescrollt.
 *
 * Das Composable kapselt 1–6, gibt `lines` plus `containerRef` zurück und
 * delegiert das Pacing/Cleanup an `usePolling`.
 *
 * Schnittstellen:
 *   - **Append:** Konsument liefert nur `fetcher` (+ optional `parseLine`).
 *   - **Cursor:** intern; Konsument hat keinen Zugriff (außer `reset()`).
 *   - **Scroll:** Konsument hängt `containerRef` an sein Log-Element; das
 *     Composable scrollt nach jedem Append ans Ende. Auf `null` deaktiviert.
 */

import { nextTick, ref, type Ref } from 'vue'

import { usePolling, type UsePollingReturn } from './usePolling'

/** Minimal interface for the stickyScroll bridge accepted by this composable. */
export interface StickyScrollBridge {
  markAppended: (delta?: number) => void
}

/** Shape of each API-Envelope page this composable accepts. */
interface LogPage<TRaw> {
  success?: boolean
  data?: {
    lines?: TRaw[]
    logs?: TRaw[]
    next_line?: number
    total_lines?: number
  }
}

export interface UseIncrementalLogPollingArgs<TRaw, TEntry> {
  fetcher: (sinceLine: number) => Promise<LogPage<TRaw> | null | undefined>
  intervalMs?: number
  parseLine?: ((raw: TRaw) => TEntry | null) | null
  stickyScroll?: StickyScrollBridge | null
}

export interface UseIncrementalLogPollingReturn<TEntry> {
  lines: Ref<TEntry[]>
  containerRef: Ref<HTMLElement | null>
  polling: UsePollingReturn
  reset: () => void
  tick: () => Promise<void>
}

export function useIncrementalLogPolling<TRaw = unknown, TEntry = TRaw>({
  fetcher,
  intervalMs = 2000,
  parseLine = null,
  stickyScroll = null,
}: UseIncrementalLogPollingArgs<TRaw, TEntry>): UseIncrementalLogPollingReturn<TEntry> {
  const lines = ref<TEntry[]>([]) as Ref<TEntry[]>
  const containerRef = ref<HTMLElement | null>(null)
  const sinceLine = ref(0)

  async function tick(): Promise<void> {
    let res: LogPage<TRaw> | null | undefined
    try {
      res = await fetcher(sinceLine.value)
    } catch {
      return
    }
    if (!res?.success) return

    const payload = res.data ?? {}
    const incoming = payload.lines ?? payload.logs
    if (!Array.isArray(incoming) || incoming.length === 0) return

    let appendedCount = 0
    for (const raw of incoming) {
      const entry = parseLine ? parseLine(raw) : (raw as unknown as TEntry)
      if (entry !== null && entry !== undefined) {
        lines.value.push(entry)
        appendedCount += 1
      }
    }

    sinceLine.value = payload.next_line ?? payload.total_lines ?? sinceLine.value

    if (appendedCount > 0) {
      if (stickyScroll && typeof stickyScroll.markAppended === 'function') {
        nextTick(() => stickyScroll.markAppended(appendedCount))
      } else {
        nextTick(() => {
          const el = containerRef.value
          if (el) el.scrollTop = el.scrollHeight
        })
      }
    }
  }

  const polling = usePolling(tick, intervalMs)

  function reset(): void {
    lines.value = []
    sinceLine.value = 0
  }

  return { lines, containerRef, polling, reset, tick }
}
