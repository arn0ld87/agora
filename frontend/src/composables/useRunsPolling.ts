/**
 * useRunsPolling — dünner Wrapper um usePolling für die Runs-Liste.
 *
 * Validiert jede API-Antwort via RunsListResponseSchema (Zod).
 * Bei Parse-Fehler: error gesetzt, alte Liste bleibt erhalten (last-known-good).
 */
import { ref, type Ref } from 'vue'
import { listRuns } from '../api/runs'
import { ApiError } from '../api/envelope'
import { RunsListResponseSchema } from '../contracts/runsContract'
import type { RunDetail } from '../contracts/runsContract'
import { usePolling } from './usePolling'
import { onListInvalidated } from '../realtime/listInvalidation'

export interface UseRunsPollingReturn {
  runs: Ref<RunDetail[]>
  loading: Ref<boolean>
  error: Ref<string>
  isRunning: Ref<boolean>
  start: () => Promise<void>
  stop: () => void
  refresh: () => Promise<void>
}

export function useRunsPolling(intervalMs: number | Ref<number> = 5000): UseRunsPollingReturn {
  const runs = ref<RunDetail[]>([])
  const loading = ref(false)
  const error = ref('')

  // Polling und Realtime-Signal (#1618) können sich überlappen: nur der
  // zuletzt gestartete Lauf schreibt, eine überholte Antwort wird verworfen.
  let loadSeq = 0

  async function tick(): Promise<void> {
    const seq = ++loadSeq
    loading.value = true
    try {
      // axios interceptor returns response.data (the full envelope body)
      // For success: { success: true, data: { runs: [...], total: N, aggregation: ... } }
      const envelope = await listRuns()
      if (seq !== loadSeq) return
      // listRuns resolves to the envelope body; data contains RunsListResponse
      const payload = (envelope as { data?: unknown }).data
      const parsed = RunsListResponseSchema.safeParse(payload)
      if (!parsed.success) {
        error.value = `Schema-Drift: ${parsed.error.issues[0]?.message ?? 'unbekannt'}`
        // last-known-good: runs.value bleibt unverändert
        return
      }
      runs.value = parsed.data.runs
      error.value = ''
    } catch (e) {
      if (seq !== loadSeq) return
      if (e instanceof ApiError) {
        error.value = e.message
      } else {
        error.value = e instanceof Error ? e.message : 'Netzwerkfehler'
      }
    } finally {
      if (seq === loadSeq) loading.value = false
    }
  }

  const polling = usePolling(tick, intervalMs, { pauseWhenHidden: true })

  // Realtime (#1618): solange gepollt wird, lädt eine Run-Änderung im
  // Workspace sofort nach. Das Polling bleibt die Rückfallebene.
  let stopRealtime: (() => void) | null = null

  return {
    runs,
    loading,
    error,
    isRunning: polling.isRunning,
    start: () => {
      // Direkt nachladen, nicht über polling.tick(): der überspringt, solange
      // ein Takt läuft, und das Signal ginge verloren.
      stopRealtime ??= onListInvalidated(['runs'], () => {
        void tick()
      })
      return polling.start({ immediate: true })
    },
    stop: () => {
      stopRealtime?.()
      stopRealtime = null
      polling.stop()
    },
    refresh: polling.tick,
  }
}
