/**
 * Reiter des Lauf-Arbeitsbereichs (Bauplan 6.2, "Zwischen Etappe 2 und ...").
 * Ziele sind Route-Namen mit Params, nie zusammengebaute Pfade. Bis zur
 * Etappe der jeweiligen Zeile führen Personas, Simulation, Bericht und
 * Interviews auf die bestehenden Ansichten.
 */
import type { RouteTarget } from './runStageState'

export type RunTabKey = 'overview' | 'graph' | 'personas' | 'simulation' | 'report' | 'interviews'

export interface RunTab {
  key: RunTabKey
  to: RouteTarget | null
  /** Schlüssel unter `views.run.disabled.<key>`. */
  disabledReason: string | null
}

export interface RunTabInput {
  simulationId: string
  /** `null`, solange das Projekt nicht aus dem Lauf aufgelöst werden konnte. */
  projectId: string | null
  /** Jüngster Bericht des Laufs, `null` ohne Bericht. */
  latestReportId: string | null
}

export function deriveRunTabs(input: RunTabInput): RunTab[] {
  const { simulationId, projectId, latestReportId } = input
  return [
    { key: 'overview', to: { name: 'RunOverview', params: { simulationId } }, disabledReason: null },
    { key: 'graph', to: { name: 'RunGraph', params: { simulationId } }, disabledReason: null },
    projectId
      ? { key: 'personas', to: { name: 'StepEnvSetup', params: { projectId } }, disabledReason: null }
      : { key: 'personas', to: null, disabledReason: 'noProject' },
    { key: 'simulation', to: { name: 'StepSimulationFeed', params: { simulationId } }, disabledReason: null },
    latestReportId
      ? { key: 'report', to: { name: 'StepReport', params: { reportId: latestReportId } }, disabledReason: null }
      : { key: 'report', to: null, disabledReason: 'noReport' },
    { key: 'interviews', to: { name: 'RunInterviewsLegacy', params: { simulationId } }, disabledReason: null },
  ]
}
