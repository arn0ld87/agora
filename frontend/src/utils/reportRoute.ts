import type { RouteLocationRaw } from 'vue-router'
import { asRunRegistryId, isSimulationId } from '../contracts/runIdentifiers'

/**
 * Zielroute fuer die Report-Ansicht.
 *
 * Issue #764 / PR #975: `simulation_id` und `run_id` sind nicht identisch —
 * die Run-Registry vergibt beim Start eine eigene UUID, die `/api/runs/<id>`
 * zwingend braucht. Sie erreicht `StepReportView` ausschliesslich ueber den
 * Query-Parameter `?runId=<id>`. Jede Navigation auf eine neue `reportId`
 * (Report-Start, Regenerieren) muss ihn deshalb mitfuehren, sonst faellt
 * `Step4Report.loadRunUsage()` still auf die `simulationId` zurueck.
 *
 * Nur echte `run_…`-IDs landen im Query. Ein `sim_…`-Wert waere hier kein
 * brauchbarer Naeherungswert, sondern eine falsche Auskunft: `/api/runs/sim_…`
 * antwortet mit 404, der Aufrufer liest das als "kein Lauf-Routing" und zeigt
 * den Workspace-Default an, obwohl der Lauf mit einem anderen Modell lief.
 */
export function buildReportRoute(reportId: string, runId?: string): RouteLocationRaw {
  const registryRunId = asRunRegistryId(runId)
  return {
    name: 'Report',
    params: { reportId },
    ...(registryRunId ? { query: { runId: registryRunId } } : {}),
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

/**
 * Sentinel-Wert fuer `reportId`, solange noch kein Report existiert.
 *
 * Issue #1023 (Befund B-26): `goReport()` in Step3Simulation.vue rief
 * bisher `generateReport()` direkt auf und startete damit den teuersten
 * Pipeline-Schritt ungefragt und mit dem Workspace-Default-Modell. Die
 * Report-Route verlangt aber zwingend einen `:reportId`-Pfad-Parameter —
 * es gibt keinen Report, den man stattdessen referenzieren koennte. Der
 * Sentinel `'new'` spiegelt die bereits etablierte Konvention aus
 * `useGraphBuildPipeline.ts` (`currentProjectId.value === 'new'`) fuer
 * "noch keine ID vorhanden". `StepReportView.vue` uebersetzt ihn zurueck
 * auf ein leeres `reportId`, damit `Step4Report`s bestehender
 * Bestaetigungs-Block (`v-if="reportPending && phase === 0"`) greift.
 */
export const PENDING_REPORT_ID = 'new'

/** Query-Schluessel fuer die Simulation-ID auf der (noch reportlosen) Report-Route. */
export const REPORT_SIMULATION_ID_QUERY_KEY = 'simulationId'

/**
 * Zielroute fuer den "bereit, aber noch nicht gestartet"-Zustand von
 * Schritt 4. Schritt 3 navigiert hierher, statt selbst `generateReport()`
 * aufzurufen — der Nutzer startet den Report erst explizit in Schritt 4.
 */
export function buildReportReadyRoute(params: {
  runId?: string | null
  simulationId: string
}): RouteLocationRaw {
  const query: Record<string, string> = {
    [REPORT_SIMULATION_ID_QUERY_KEY]: params.simulationId,
  }
  // Schritt 3 reicht `runId.value || props.simulationId` durch: nach einem
  // Reload ist die Registry-ID nicht mehr im Speicher und der Fallback liefert
  // eine `sim_…`-ID. Sie hier zu verwerfen ist der ehrlichere Zustand — Schritt
  // 4 kennt dann kein Lauf-Routing und sagt das auch, statt ein falsches Modell
  // aus einem fehlgeschlagenen `/api/runs/sim_…`-Aufruf abzuleiten.
  const registryRunId = asRunRegistryId(params.runId)
  if (registryRunId) query.runId = registryRunId
  return {
    name: 'Report',
    params: { reportId: PENDING_REPORT_ID },
    query,
  }
}
