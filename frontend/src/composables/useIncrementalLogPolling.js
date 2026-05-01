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

import { nextTick, ref } from 'vue'

import { usePolling } from './usePolling'

/**
 * @template TRaw, TEntry
 * @param {object} args
 * @param {(sinceLine: number) => Promise<{ success?: boolean, data?: { lines?: TRaw[], logs?: TRaw[], next_line?: number, total_lines?: number } } | null>} args.fetcher
 *   – Lieferant der Log-Page; bekommt den aktuellen Cursor und gibt das API-Envelope zurück.
 * @param {number} [args.intervalMs=2000] – Pacing.
 * @param {(raw: TRaw) => TEntry|null} [args.parseLine] – optionale Transformation; `null` → Eintrag wird verworfen.
 * @param {{ markAppended: (delta?: number) => void } | null} [args.stickyScroll]
 *   – Optionale `useStickyScroll`-Instanz. Wenn übergeben, ruft das Composable
 *     `stickyScroll.markAppended(deltaCount)` statt blind `scrollTop = scrollHeight`,
 *     damit ein Nutzer-Scrollback respektiert wird (Issue #131, baut auf #130 auf).
 * @returns {{
 *   lines: import('vue').Ref<TEntry[]>,
 *   containerRef: import('vue').Ref<HTMLElement|null>,
 *   polling: ReturnType<typeof usePolling>,
 *   reset: () => void,
 *   tick: () => Promise<void>
 * }}
 */
export function useIncrementalLogPolling({ fetcher, intervalMs = 2000, parseLine = null, stickyScroll = null }) {
  const lines = ref([])
  const containerRef = ref(null)
  const sinceLine = ref(0)

  async function tick() {
    let res
    try {
      res = await fetcher(sinceLine.value)
    } catch {
      return
    }
    if (!res?.success) return

    const payload = res.data || {}
    const incoming = payload.lines || payload.logs
    if (!Array.isArray(incoming) || incoming.length === 0) return

    let appendedCount = 0
    for (const raw of incoming) {
      const entry = parseLine ? parseLine(raw) : raw
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

  function reset() {
    lines.value = []
    sinceLine.value = 0
  }

  return { lines, containerRef, polling, reset, tick }
}
