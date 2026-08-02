import type { RouteLocationRaw } from 'vue-router'
import { isSimulationId } from '../contracts/runIdentifiers'

/**
 * Zielroute fuer die Report-Ansicht.
 *
 * Issue #764 / PR #975: `simulation_id` und `run_id` sind nicht identisch —
 * die Run-Registry vergibt beim Start eine eigene UUID, die `/api/runs/<id>`
 * zwingend braucht. Sie erreicht `StepReportView` ausschliesslich ueber den
 * Query-Parameter `?runId=<id>`. Jede Navigation auf eine neue `reportId`
 * (Report-Start, Regenerieren) muss ihn deshalb mitfuehren, sonst faellt
 * `Step4Report.loadRunUsage()` still auf die `simulationId` zurueck.
 */
export function buildReportRoute(reportId: string, runId?: string): RouteLocationRaw {
  return {
    name: 'Report',
    params: { reportId },
    ...(runId ? { query: { runId } } : {}),
  }
}

/**
 * Query-Schlüssel für die Simulation-ID auf der Interaktions-Route.
 *
 * Issue #1023 (Regression aus PR #997): `StepInteractionView.vue` las den
 * gleichen Schlüssel wie die Report-Route (`runId`) und reichte den Wert
 * als `simulation_id` durch — obwohl `runId` dort ausdrücklich die
 * Registry-Run-ID ist. Ein eigener, sprechender Schlüssel verhindert die
 * Verwechslung strukturell statt nur durch Konvention.
 */
export const INTERACTION_SIMULATION_ID_QUERY_KEY = 'simId'

/**
 * Zielroute fuer die Interaktions-Ansicht (Schritt 5).
 *
 * Nimmt nur echte Simulation-IDs (`sim_…`) in den Query auf. Eine
 * Run-Registry-ID oder ein sonst unpassender Wert wird verworfen, statt
 * sie unter falschem Namen weiterzureichen.
 */
export function buildInteractionRoute(
  reportId: string,
  simulationId?: string | null,
): RouteLocationRaw {
  const validSimulationId = isSimulationId(simulationId) ? simulationId : undefined
  return {
    name: 'Interaction',
    params: { reportId },
    ...(validSimulationId
      ? { query: { [INTERACTION_SIMULATION_ID_QUERY_KEY]: validSimulationId } }
      : {}),
  }
}
