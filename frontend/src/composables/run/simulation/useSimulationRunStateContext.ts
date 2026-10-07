/**
 * Gemeinsamer Laufstand der Simulation (#1801, Etappe 4): Die Hülle legt eine
 * Instanz von `useSimulationRunState` an und gibt sie per provide/inject an Kopf
 * und Kind-Ansichten. So gibt es je Lauf genau einen SSE-Strom und ein Polling
 * statt drei. Ohne Hülle (Einzeltest, Einzelmontage) legt die Komponente ihre
 * eigene Instanz an.
 */
import { inject, provide, type InjectionKey } from 'vue'
import {
  useSimulationRunState,
  type SimulationRunState,
  type SimulationRunStateOptions,
} from './useSimulationRunState'

export const SIMULATION_RUN_STATE_KEY: InjectionKey<SimulationRunState> = Symbol('simulation-run-state')

/** Hülle: eine Instanz anlegen und an die Nachfahren geben. */
export function provideSimulationRunState(
  simulationId: () => string,
  options: SimulationRunStateOptions = {},
): SimulationRunState {
  const state = useSimulationRunState(simulationId, options)
  provide(SIMULATION_RUN_STATE_KEY, state)
  return state
}

/** Nachfahre: die Instanz der Hülle nutzen, sonst eine eigene anlegen. */
export function useSimulationRunStateContext(
  simulationId: () => string,
  options: SimulationRunStateOptions = {},
): SimulationRunState {
  return inject(SIMULATION_RUN_STATE_KEY, null) ?? useSimulationRunState(simulationId, options)
}
