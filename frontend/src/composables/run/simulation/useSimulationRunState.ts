/**
 * Laufstand der Simulation für den Kopf am Lauf (#1801, Ticket D).
 *
 * Quellen: `GET /run-status` (einmal beim Laden und bei beendeten Läufen),
 * SSE `state`/`control` plus Polling `run-status/detail` alle 2,5 s solange der
 * Lauf aktiv ist, und `GET /api/runs/<run_id>` für Kosten, Abbruchgrund und
 * Fehlertext des Jobs. Jede Antwort läuft durch ein schmales Zod-Schema; ein
 * Fehler steht in `error` und wird nie verschluckt. Aufgeräumt wird beim
 * Wechsel der Kennung und beim Verlassen des Scopes.
 */
import { computed, getCurrentScope, onScopeDispose, ref, watch, type ComputedRef, type Ref } from 'vue'
import { z } from 'zod'
import { getRunStatus, getRunStatusDetail } from '@/api/simulation'
import { getRun } from '@/api/runs'
import { useEventStream } from '@/composables/useEventStream'
import { usePolling } from '@/composables/usePolling'
import type { StageStateKind } from '@/composables/run/runStageState'
import { describeError, readEnvelope } from './simulationEnvelope'

export const SIM_POLL_INTERVAL_MS = 2500

const count = z.number().int().min(0).nullish()

/** `GET /run-status` und `/run-status/detail` (SimulationRunState.to_dict). */
export const RunStatusPayloadSchema = z
  .object({
    runner_status: z.string().nullish(),
    current_round: count,
    total_rounds: count,
    paused: z.boolean().nullish(),
    twitter_actions_count: count,
    reddit_actions_count: count,
    error: z.string().nullish(),
  })
  .passthrough()
export type RunStatusPayload = z.infer<typeof RunStatusPayloadSchema>

/** SSE `control`: Pause-Flag. */
export const ControlPayloadSchema = z.object({ paused: z.boolean() }).passthrough()

/** `GET /api/runs/<id>`: nur, was der Kopf braucht. */
export const RunJobPayloadSchema = z
  .object({
    status: z.string().nullish(),
    termination_reason: z.string().nullish(),
    error: z.string().nullish(),
    usage: z
      .object({ totals: z.object({ cost_micros: z.number().int().min(0).nullish() }).passthrough() })
      .passthrough()
      .nullish(),
  })
  .passthrough()

const ACTIVE = new Set(['starting', 'running', 'paused', 'stopping'])
const TERMINAL = new Set(['completed', 'failed', 'stopped'])

export interface SimulationRunStateOptions {
  /** RunRegistry-ID des Simulationsjobs, falls schon bekannt (Arbeitsbereich oder Startantwort). */
  runId?: () => string | null | undefined
}

export interface SimulationRunState {
  runnerStatus: Ref<string | null>
  stateKind: ComputedRef<StageStateKind>
  currentRound: Ref<number | null>
  totalRounds: Ref<number | null>
  paused: Ref<boolean>
  twitterActions: Ref<number | null>
  redditActions: Ref<number | null>
  totalActions: ComputedRef<number | null>
  /** Kosten in Mikro-USD; `null` = nicht erfasst. */
  costMicros: Ref<number | null>
  runId: ComputedRef<string | null>
  terminationReason: Ref<string | null>
  /** Fehlertext des Jobs (Backend), nicht der Ladefehler. */
  runError: Ref<string | null>
  /** Ladefehler (Transport oder Vertragsbruch), sichtbar zu machen. */
  error: Ref<string | null>
  loading: Ref<boolean>
  reload: () => Promise<void>
  /** Übernimmt die run_id aus der Startantwort und lädt neu. */
  adoptRunId: (id: string | null) => Promise<void>
}

export function useSimulationRunState(
  simulationId: () => string,
  options: SimulationRunStateOptions = {},
): SimulationRunState {
  const runnerStatus = ref<string | null>(null)
  const currentRound = ref<number | null>(null)
  const totalRounds = ref<number | null>(null)
  const paused = ref(false)
  const twitterActions = ref<number | null>(null)
  const redditActions = ref<number | null>(null)
  const costMicros = ref<number | null>(null)
  const terminationReason = ref<string | null>(null)
  const runError = ref<string | null>(null)
  const error = ref<string | null>(null)
  const loading = ref(false)
  const adopted = ref<string | null>(null)
  let generation = 0
  let tracking = false

  const runId = computed(() => adopted.value || options.runId?.() || null)

  const totalActions = computed<number | null>(() => {
    if (twitterActions.value === null && redditActions.value === null) return null
    return (twitterActions.value ?? 0) + (redditActions.value ?? 0)
  })

  const stateKind = computed<StageStateKind>(() => {
    const s = runnerStatus.value
    if (!s || s === 'idle' || s === 'ready') return 'notStarted'
    if (s === 'starting') return 'queued'
    if (s === 'running' || s === 'stopping') return paused.value ? 'paused' : 'running'
    if (s === 'paused') return 'paused'
    if (s === 'completed') return 'done'
    if (s === 'stopped' || s === 'failed') {
      const reason = terminationReason.value ?? ''
      if (reason.startsWith('budget_')) return 'budget'
      if (reason === 'user_stop' || reason === 'user_cancel' || s === 'stopped') return 'stopped'
      return 'failed'
    }
    return 'notRecorded'
  })

  function apply(payload: RunStatusPayload): void {
    if (payload.runner_status !== undefined) runnerStatus.value = payload.runner_status ?? null
    if (payload.current_round !== undefined) currentRound.value = payload.current_round ?? null
    if (payload.total_rounds !== undefined) totalRounds.value = payload.total_rounds ?? null
    if (payload.paused !== undefined && payload.paused !== null) paused.value = payload.paused
    else if (payload.runner_status === 'paused') paused.value = true
    else if (payload.runner_status === 'running') paused.value = false
    if (payload.twitter_actions_count !== undefined) twitterActions.value = payload.twitter_actions_count ?? null
    if (payload.reddit_actions_count !== undefined) redditActions.value = payload.reddit_actions_count ?? null
    if (payload.error) runError.value = payload.error
  }

  const stream = useEventStream(simulationId, {
    state: (msg) => {
      const parsed = RunStatusPayloadSchema.safeParse(msg?.payload)
      if (!parsed.success) {
        error.value = `Vertragsbruch SSE state: ${parsed.error.message}`
        return
      }
      apply(parsed.data)
      onStatusApplied()
    },
    control: (msg) => {
      const parsed = ControlPayloadSchema.safeParse(msg?.payload)
      if (!parsed.success) {
        error.value = `Vertragsbruch SSE control: ${parsed.error.message}`
        return
      }
      paused.value = parsed.data.paused
    },
  })

  const polling = usePolling(pollOnce, SIM_POLL_INTERVAL_MS, {
    onError: (err) => {
      error.value = describeError(err)
    },
  })

  async function pollOnce(): Promise<void> {
    const mine = generation
    const id = simulationId()
    if (!id) return
    const payload = readEnvelope(await getRunStatusDetail(id), RunStatusPayloadSchema, `GET /api/simulation/${id}/run-status/detail`)
    if (mine !== generation) return
    apply(payload)
    error.value = null
    onStatusApplied()
    // Endete der Lauf in diesem Tick, hat onStatusApplied() die Kosten schon nachgeladen.
    if (tracking) await refreshJob()
  }

  function startTracking(): void {
    if (tracking) return
    tracking = true
    void stream.start()
    void polling.start()
  }

  function stopTracking(): void {
    tracking = false
    stream.stop()
    polling.stop()
  }

  function onStatusApplied(): void {
    const s = runnerStatus.value
    if (s && ACTIVE.has(s)) {
      startTracking()
    } else if (tracking && (!s || TERMINAL.has(s) || s === 'idle' || s === 'ready')) {
      stopTracking()
      void refreshJob()
    }
  }

  async function refreshJob(): Promise<void> {
    const id = runId.value
    if (!id) return
    const mine = generation
    try {
      const job = readEnvelope(await getRun(id), RunJobPayloadSchema, `GET /api/runs/${id}`)
      if (mine !== generation) return
      costMicros.value = job.usage?.totals.cost_micros ?? null
      terminationReason.value = job.termination_reason ?? null
      if (job.error) runError.value = job.error
    } catch (err) {
      if (mine !== generation) return
      error.value = describeError(err)
    }
  }

  function reset(): void {
    generation += 1
    stopTracking()
    runnerStatus.value = null
    currentRound.value = null
    totalRounds.value = null
    paused.value = false
    twitterActions.value = null
    redditActions.value = null
    costMicros.value = null
    terminationReason.value = null
    runError.value = null
    error.value = null
    adopted.value = null
  }

  async function reload(): Promise<void> {
    const id = simulationId()
    if (!id) return
    const mine = ++generation
    loading.value = true
    error.value = null
    try {
      const payload = readEnvelope(await getRunStatus(id), RunStatusPayloadSchema, `GET /api/simulation/${id}/run-status`)
      if (mine !== generation) return
      apply(payload)
      onStatusApplied()
      await refreshJob()
    } catch (err) {
      if (mine !== generation) return
      error.value = describeError(err)
    } finally {
      if (mine === generation) loading.value = false
    }
  }

  async function adoptRunId(id: string | null): Promise<void> {
    adopted.value = id && id.length > 0 ? id : null
    await reload()
  }

  watch(
    simulationId,
    () => {
      reset()
      void reload()
    },
    { immediate: true },
  )
  // Eine neu bekannte run_id (z. B. nach dem Start im Arbeitsbereich) lädt Kosten und Grund nach.
  watch(
    () => options.runId?.() ?? null,
    (next, prev) => {
      if (next && next !== prev) void refreshJob()
    },
  )

  if (getCurrentScope()) onScopeDispose(stopTracking)

  return {
    runnerStatus,
    stateKind,
    currentRound,
    totalRounds,
    paused,
    twitterActions,
    redditActions,
    totalActions,
    costMicros,
    runId,
    terminationReason,
    runError,
    error,
    loading,
    reload,
    adoptRunId,
  }
}
