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

  async function tick(): Promise<void> {
    loading.value = true
    try {
      // axios interceptor returns response.data (the full envelope body)
      // For success: { success: true, data: { runs: [...], total: N, aggregation: ... } }
      const envelope = await listRuns()
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
      if (e instanceof ApiError) {
        error.value = e.message
      } else {
        error.value = e instanceof Error ? e.message : 'Netzwerkfehler'
      }
    } finally {
      loading.value = false
    }
  }

  const polling = usePolling(tick, intervalMs, { pauseWhenHidden: true })

  return {
    runs,
    loading,
    error,
    isRunning: polling.isRunning,
    start: () => polling.start({ immediate: true }),
    stop: polling.stop,
    refresh: polling.tick,
  }
}
