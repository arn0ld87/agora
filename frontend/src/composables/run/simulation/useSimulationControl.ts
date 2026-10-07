/**
 * Steuerung der Simulation am Lauf (#1801, Ticket D): Starten, Stoppen,
 * Pausieren, Fortsetzen, Abbrechen. Löst `Step3Simulation.vue` ab (#1801; gleiche Request-Felder, gleicher Modell-Resolver, Run-Override wird nach dem
 * Start verbraucht); die Startwerte kommen aus dem vorgemerkten Startdialog
 * (`readPendingRunParams`) und werden nach erfolgreichem Start entfernt.
 * Fehlertexte des Backends (auch Budget und Rate-Limit) bleiben unverändert
 * sichtbar in `error`; nichts wird in eine Erfolgsmeldung umgedeutet.
 */
import { getCurrentInstance, onMounted, ref, type Ref } from 'vue'
import { z } from 'zod'
import {
  pauseSimulation,
  resumeSimulation,
  startSimulation,
  stopSimulation,
  type SimulationPlatform,
  type StartSimulationData,
} from '@/api/simulation'
import { cancelRun } from '@/api/runs'
import { useRunModelResolver } from '@/composables/useRunModelResolver'
import { clearPendingRunParams, readPendingRunParams } from '@/composables/new-run/pendingRunParams'
import { clearRunModelOverride, getRunModelOverride } from '@/store/runModelOverride'
import { useLlmRoutingDefaultsStore } from '@/store/aiModels'
import { describeError, readEnvelope } from './simulationEnvelope'

export type ControlAction = 'start' | 'stop' | 'pause' | 'resume' | 'cancel'

const StartDataSchema = z.object({ run_id: z.string().nullish() }).passthrough()
const AnyData = z.unknown()
const PARALLEL = 'parallel' as unknown as SimulationPlatform

export interface StartResult {
  /** RunRegistry-ID des Simulationsjobs, falls das Backend sie liefert. */
  runId: string | null
}

export interface SimulationControl {
  /** Laufende Aktion; `null`, wenn nichts läuft. */
  busy: Ref<ControlAction | null>
  /** Fehlertext der letzten Aktion (Backend-Text unverändert). */
  error: Ref<string | null>
  start: () => Promise<StartResult | null>
  stop: () => Promise<boolean>
  pause: () => Promise<boolean>
  resume: () => Promise<boolean>
  cancel: () => Promise<boolean>
  /** Modell, das der nächste Start verwenden wird (Run-Override, sonst Routing-Standard); `null` = keins erfasst. */
  plannedModel: () => string | null
}

export function useSimulationControl(simulationId: () => string): SimulationControl {
  const busy = ref<ControlAction | null>(null)
  const error = ref<string | null>(null)
  const { resolveRunModel } = useRunModelResolver()
  const defaults = useLlmRoutingDefaultsStore()

  if (getCurrentInstance()) {
    onMounted(async () => {
      if (defaults.hasLoadedOnce) return
      try {
        await defaults.load()
      } catch (err) {
        console.warn('[sim-control] Routing-Standard nicht ladbar', err)
      }
    })
  }

  function plannedModel(): string | null {
    const override = getRunModelOverride()
    if (override?.model_id) return override.model_id
    if (!defaults.hasLoadedOnce) return null
    return defaults.effectiveRouteForStage('simulation_rounds').model || null
  }

  async function run<T>(action: ControlAction, fn: () => Promise<T>, failed: T): Promise<T> {
    if (busy.value) return failed
    busy.value = action
    error.value = null
    try {
      return await fn()
    } catch (err) {
      error.value = describeError(err)
      return failed
    } finally {
      busy.value = null
    }
  }

  function start(): Promise<StartResult | null> {
    return run<StartResult | null>(
      'start',
      async () => {
        const id = simulationId()
        if (!id) throw new Error('simulation_id fehlt')
        const params: StartSimulationData = {
          simulation_id: id,
          // Der Bestand sendet 'parallel' (beide Netzwerke); `SimulationPlatform` kennt den Wert noch nicht.
          platform: PARALLEL,
          enable_graph_memory_update: false,
        }
        // Startwerte des Dialogs "Neuer Lauf": ohne Eintrag gelten die Auto-Werte des Backends.
        const pending = readPendingRunParams(id)
        if (pending?.maxRounds) params.max_rounds = pending.maxRounds
        if (pending?.budget) params.budget = pending.budget
        if (pending?.simulationDays) params.simulation_days = pending.simulationDays
        // Autoritative (Connection, Modell)-Auswahl: Run-Override vor Kanon; ohne beides entscheidet das Backend-Routing.
        const { ref: selection, usedRunOverride } = await resolveRunModel()
        if (selection && selection.provider_connection_id && selection.model_id) {
          params.ai_model_ref = {
            provider_connection_id: selection.provider_connection_id,
            model_id: selection.model_id,
            source: selection.source ?? 'explicit',
          }
        }
        const data = readEnvelope(await startSimulation(params), StartDataSchema, 'POST /api/simulation/start')
        // Consume-on-success: Override und vorgemerkte Startwerte gelten genau für diesen Start.
        if (usedRunOverride) clearRunModelOverride()
        clearPendingRunParams(id)
        return { runId: data.run_id && data.run_id.length > 0 ? data.run_id : null }
      },
      null,
    )
  }

  function stop(): Promise<boolean> {
    return run(
      'stop',
      async () => {
        readEnvelope(await stopSimulation({ simulation_id: simulationId() }), AnyData, 'POST /api/simulation/stop')
        return true
      },
      false,
    )
  }

  function pause(): Promise<boolean> {
    return run(
      'pause',
      async () => {
        readEnvelope(await pauseSimulation(simulationId()), AnyData, 'POST /api/simulation/<id>/pause')
        return true
      },
      false,
    )
  }

  function resume(): Promise<boolean> {
    return run(
      'resume',
      async () => {
        readEnvelope(await resumeSimulation(simulationId()), AnyData, 'POST /api/simulation/<id>/resume')
        return true
      },
      false,
    )
  }

  function cancel(): Promise<boolean> {
    return run(
      'cancel',
      async () => {
        // Wie im Bestand mit der simulation_id: POST /api/runs/<id>/cancel löst sim_ und run_ auf.
        readEnvelope(await cancelRun(simulationId()), AnyData, 'POST /api/runs/<id>/cancel')
        return true
      },
      false,
    )
  }

  return { busy, error, start, stop, pause, resume, cancel, plannedModel }
}
