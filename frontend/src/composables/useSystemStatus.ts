/**
 * useSystemStatus — Polling-Wrapper um GET /api/status.
 *
 * Zod-validiert. Bei Schema-Drift bleibt `status` last-known-good erhalten.
 * Backend liefert ein flaches Envelope (json_success(**extra)), wir akzeptieren
 * beide Formen (data.* und top-level).
 */
import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSystemStatus } from '../api/status'
import { ApiError } from '../api/envelope'
import {
  SystemStatusResponseSchema,
  type SystemStatusResponse,
} from '../contracts/systemStatusContract'
import { usePolling } from './usePolling'

export interface UseSystemStatusReturn {
  status: Ref<SystemStatusResponse | null>
  loading: Ref<boolean>
  error: Ref<string>
  isRunning: Ref<boolean>
  start: () => Promise<void>
  stop: () => void
  refresh: () => Promise<void>
}

function extractCandidate(envelope: unknown): unknown {
  if (envelope == null || typeof envelope !== 'object') return null
  const env = envelope as Record<string, unknown>
  if (env['data'] && typeof env['data'] === 'object') {
    return env['data']
  }
  // Flat-Envelope: backend/neo4j/ollama/disk/timestamp leben direkt am Root.
  const { success: _success, ...rest } = env
  return rest
}

export function useSystemStatus(
  intervalMs: number | Ref<number> = 15000,
): UseSystemStatusReturn {
  const status = ref<SystemStatusResponse | null>(null)
  const loading = ref(false)
  const error = ref('')
  const { t } = useI18n()

  async function tick(): Promise<void> {
    loading.value = true
    try {
      const envelope = await getSystemStatus()
      const candidate = extractCandidate(envelope)
      const parsed = SystemStatusResponseSchema.safeParse(candidate)
      if (!parsed.success) {
        error.value = `Schema-Drift: ${parsed.error.issues[0]?.message ?? 'unbekannt'}`
        return
      }
      status.value = parsed.data
      error.value = ''
    } catch (e) {
      if (e instanceof ApiError) {
        error.value = e.message
      } else {
        error.value = e instanceof Error ? e.message : t('errors.network')
      }
    } finally {
      loading.value = false
    }
  }

  const polling = usePolling(tick, intervalMs, { pauseWhenHidden: true })

  return {
    status,
    loading,
    error,
    isRunning: polling.isRunning,
    start: () => polling.start({ immediate: true }),
    stop: polling.stop,
    refresh: polling.tick,
  }
}
