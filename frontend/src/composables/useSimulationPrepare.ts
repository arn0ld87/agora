/**
 * Composable for the Simulation-Prepare lifecycle (Sub-Slice 34, Refs #203).
 *
 * Extracted from Step2EnvSetup.vue to reduce that component below 800 LOC.
 *
 * Wraps the backend endpoints:
 *   POST /api/simulation/prepare
 *   POST /api/simulation/prepare/status
 *   GET  /api/simulation/<id>/profiles/realtime
 *   GET  /api/simulation/<id>/config/realtime
 *
 * Phase model:
 *   0 — idle
 *   1 — personas being generated
 *   2 — config being generated
 *   3 — ready (prepare complete)
 */

import { ref, onUnmounted, type Ref } from 'vue'
import { parsePersonaTarget } from '../contracts/personaTargetContract'
import {
  prepareSimulation,
  getPrepareStatus,
  getSimulationProfilesRealtime,
  getSimulationConfigRealtime,
  type PrepareSimulationData,
  type TaskStatusData,
  type ProfileRecord,
} from '../api/simulation'
import { usePolling } from './usePolling'

// -------------------------------------------------------------------------
// Public types
// -------------------------------------------------------------------------

export interface PrepareOptions {
  /** Merged payload overrides forwarded to POST /api/simulation/prepare */
  payload: PrepareSimulationData
  /** Called when the backend transitions through stages or emits a log message */
  onLog: (msg: string) => void
  /** Called with 'processing' | 'completed' | 'error' to sync outer wizard state */
  onStatusChange: (status: string) => void
}

export interface SimulationPrepareState {
  /** 0 idle · 1 personas · 2 config · 3 ready */
  phase: Ref<number>
  isPreparing: Ref<boolean>
  prepareProgress: Ref<number>
  progressMessage: Ref<string>
  profiles: Ref<ProfileRecord[]>
  expectedTotal: Ref<number | null>
  /**
   * Der Persona-Floor hat das Ziel über die Entitätenzahl angehoben
   * (Issue #1034) — die Oberfläche macht das kenntlich, sonst wirkt der
   * Nenner willkürlich, wenn sieben Entitäten fünfzig Personas ergeben.
   */
  personaFloorApplied: Ref<boolean>
  simulationConfig: Ref<Record<string, unknown> | null>
  error: Ref<string | null>
}

export interface UseSimulationPrepareReturn extends SimulationPrepareState {
  /** Fetch the current profiles list once from the realtime endpoint. */
  fetchProfilesRealtime: () => Promise<void>
  /** Kick off a prepare run. Returns false if aborted early (e.g. no simulationId). */
  startPrepare: (opts: PrepareOptions) => Promise<boolean>
  /** Probe whether the simulation is already prepared and hydrate state if so. */
  probeAlreadyPrepared: (simulationId: string, opts: Pick<PrepareOptions, 'onLog' | 'onStatusChange'>) => Promise<void>
  /** Reset all reactive state to initial values (e.g. on sim change). */
  reset: () => void
}

// -------------------------------------------------------------------------
// Private helpers
// -------------------------------------------------------------------------

interface PrepareTaskStatus {
  status?: string
  progress?: number
  message?: string
  error?: string | null
  progress_detail?: {
    current_stage?: string
  }
}

interface PrepareEnvelope {
  success?: boolean
  error?: string
  data?: {
    already_prepared?: boolean
    task_id?: string
    expected_entities_count?: number
    persona_target?: unknown
  }
}

interface ProfilesEnvelope {
  success?: boolean
  data?: {
    profiles?: ProfileRecord[]
  }
}

interface ConfigEnvelope {
  success?: boolean
  data?: {
    config?: Record<string, unknown>
  }
}

interface StatusEnvelope {
  success?: boolean
  data?: PrepareTaskStatus
}

// -------------------------------------------------------------------------
// Composable
// -------------------------------------------------------------------------

export function useSimulationPrepare(): UseSimulationPrepareReturn {
  // --- State ---
  const phase = ref(0)
  const isPreparing = ref(false)
  const prepareProgress = ref(0)
  const progressMessage = ref('')
  const profiles = ref<ProfileRecord[]>([])
  const expectedTotal = ref<number | null>(null)
  const personaFloorApplied = ref(false)
  const simulationConfig = ref<Record<string, unknown> | null>(null)
  const error = ref<string | null>(null)

  // Closure-scoped mutable refs for the current prepare session
  let _simulationId: string | null = null
  let _taskId: string | null = null
  let _onLog: ((msg: string) => void) | null = null
  let _onStatusChange: ((status: string) => void) | null = null

  // --- Polling instances ---
  const prepareStatusPolling = usePolling(
    () => _pollPrepareStatus(),
    2000,
    { pauseWhenHidden: false }, // keep polling even in background tab (long-running task)
  )

  const profilesPolling = usePolling(
    () => fetchProfilesRealtime(),
    3000,
    { pauseWhenHidden: false },
  )

  const configPolling = usePolling(
    () => _fetchConfigRealtime(),
    3000,
    { pauseWhenHidden: false },
  )

  // Teardown on component unmount
  onUnmounted(() => {
    prepareStatusPolling.stop()
    profilesPolling.stop()
    configPolling.stop()
  })

  // --- Internal fetch helpers ---

  async function fetchProfilesRealtime(): Promise<void> {
    if (!_simulationId) return
    try {
      // reason: service interceptor returns raw envelope body at runtime
      const res = (await getSimulationProfilesRealtime(_simulationId, 'reddit')) as unknown as ProfilesEnvelope
      if (res?.success && Array.isArray(res.data?.profiles)) {
        profiles.value = res.data.profiles
      }
    } catch {
      // swallow — realtime poll; errors are transient
    }
  }

  async function _fetchConfigRealtime(): Promise<void> {
    if (!_simulationId) return
    try {
      // reason: service interceptor returns raw envelope body at runtime
      const res = (await getSimulationConfigRealtime(_simulationId)) as unknown as ConfigEnvelope
      if (res?.success && res.data?.config) {
        simulationConfig.value = res.data.config
      }
    } catch {
      // swallow — realtime poll; errors are transient
    }
  }

  async function _loadPreparedData(): Promise<void> {
    await fetchProfilesRealtime()
    await _fetchConfigRealtime()
    phase.value = 3
    _onStatusChange?.('completed')
    isPreparing.value = false
  }

  async function _pollPrepareStatus(): Promise<void> {
    if (!_taskId) return
    try {
      // reason: service interceptor returns raw envelope body at runtime;
      // getPrepareStatus is typed as TaskStatusData but returns the envelope
      const res = (await getPrepareStatus({ task_id: _taskId } as TaskStatusData)) as unknown as StatusEnvelope
      if (res?.success && res.data) {
        const st = res.data
        prepareProgress.value = st.progress || 0
        progressMessage.value = st.message || ''

        const stage = st.progress_detail?.current_stage
        if (stage === 'generating_config' && phase.value < 2) {
          phase.value = 2
          _onLog?.('Konfiguration wird generiert…')
          void configPolling.start()
        }

        if (st.status === 'completed') {
          prepareStatusPolling.stop()
          profilesPolling.stop()
          configPolling.stop()
          await _loadPreparedData()
          _onLog?.(`Vorbereitung abgeschlossen (${profiles.value.length} Personas)`)
        } else if (st.status === 'failed') {
          const msg = st.error || 'Vorbereitung fehlgeschlagen.'
          _onLog?.(msg)
          error.value = msg
          prepareStatusPolling.stop()
          profilesPolling.stop()
          configPolling.stop()
          _onStatusChange?.('error')
          isPreparing.value = false
        }
      }
    } catch (e) {
      // Warn but don't abort — polling will retry
      console.warn('[useSimulationPrepare] pollPrepareStatus error', e)
    }
  }

  // --- Public API ---

  function reset(): void {
    phase.value = 0
    isPreparing.value = false
    prepareProgress.value = 0
    progressMessage.value = ''
    profiles.value = []
    expectedTotal.value = null
    personaFloorApplied.value = false
    simulationConfig.value = null
    error.value = null
    _simulationId = null
    _taskId = null
    _onLog = null
    _onStatusChange = null
    prepareStatusPolling.stop()
    profilesPolling.stop()
    configPolling.stop()
  }

  async function startPrepare(opts: PrepareOptions): Promise<boolean> {
    const { payload, onLog, onStatusChange } = opts

    if (!payload.simulation_id) {
      onLog('Fehler: simulationId fehlt')
      onStatusChange('error')
      return false
    }

    // Guard: no re-entrant calls while already preparing
    if (isPreparing.value) {
      console.warn('[useSimulationPrepare] startPrepare called while already preparing — no-op')
      return false
    }

    _simulationId = payload.simulation_id
    _onLog = onLog
    _onStatusChange = onStatusChange
    error.value = null

    isPreparing.value = true
    phase.value = 1
    onStatusChange('processing')
    onLog('Vorbereitung startet…')

    try {
      // reason: service interceptor returns raw envelope body at runtime
      const res = (await prepareSimulation(payload)) as unknown as PrepareEnvelope

      if (res?.success && res.data) {
        if (res.data.already_prepared) {
          onLog('Simulation bereits vorbereitet.')
          await _loadPreparedData()
          return true
        }

        _taskId = res.data.task_id ?? null
        if (!_taskId) {
          // Backend lieferte success+data ohne task_id → Polling würde sofort
          // im Guard 'if (!_taskId) return' steckenbleiben und der prepare-Flow
          // hinge dauerhaft in isPreparing=true. Fail-fast statt stiller Hang.
          const msg = 'Vorbereitung fehlgeschlagen: Backend lieferte keine task_id.'
          console.warn('[useSimulationPrepare] startPrepare: success ohne task_id', res.data)
          onLog(msg)
          error.value = msg
          onStatusChange('error')
          isPreparing.value = false
          return false
        }
        onLog(`Task gestartet: ${_taskId}`)
        // Issue #1034: Der Nenner zählt Personas, nicht Entitäten. Das
        // Backend liefert das Generierungsziel als eigenes Vertragsfeld;
        // `expected_entities_count` ist die Entitätenzahl und war als
        // Nenner falsch, sobald der Persona-Floor gegriffen hat.
        const target = parsePersonaTarget(res.data.persona_target)
        if (target) {
          expectedTotal.value = target.persona_target_count
          personaFloorApplied.value = target.floor_applied
        } else if (res.data.expected_entities_count) {
          // Ältere Backends ohne `persona_target`: lieber die alte Zahl
          // als gar keine — sie ist nur dann falsch, wenn der Floor greift.
          expectedTotal.value = res.data.expected_entities_count
        }

        void prepareStatusPolling.start()
        void profilesPolling.start()
        return true
      }

      const msg = res?.error || 'Vorbereitung fehlgeschlagen (unbekannter Fehler).'
      onLog(msg)
      error.value = msg
      onStatusChange('error')
      isPreparing.value = false
      return false
    } catch (err) {
      const e = err as { message?: string }
      const msg = e?.message || 'Netzwerkfehler bei der Vorbereitung.'
      onLog(msg)
      error.value = msg
      onStatusChange('error')
      isPreparing.value = false
      return false
    }
  }

  async function probeAlreadyPrepared(
    simulationId: string,
    opts: Pick<PrepareOptions, 'onLog' | 'onStatusChange'>,
  ): Promise<void> {
    if (!simulationId) return
    _simulationId = simulationId
    _onLog = opts.onLog
    _onStatusChange = opts.onStatusChange

    await _fetchConfigRealtime()
    if (simulationConfig.value) {
      await _loadPreparedData()
    }
  }

  return {
    // state
    phase,
    isPreparing,
    prepareProgress,
    progressMessage,
    profiles,
    expectedTotal,
    personaFloorApplied,
    simulationConfig,
    error,
    // actions
    fetchProfilesRealtime,
    startPrepare,
    probeAlreadyPrepared,
    reset,
  }
}
