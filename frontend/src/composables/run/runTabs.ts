/**
 * Reiter des Lauf-Arbeitsbereichs (Bauplan 6.2, "Zwischen Etappe 2 und ...").
 * Ziele sind Route-Namen mit Params, nie zusammengebaute Pfade. Bis zur
 * Etappe der jeweiligen Zeile führt Personas auf die bestehende Ansicht;
 * Simulation (Etappe 4), Bericht (Etappe 5) und Interviews (Etappe 6) sind
 * Kind-Routen des Laufs.
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
  /**
   * Die Berichtsstufe lässt sich starten (Simulation fertig, noch kein Bericht;
   * `deriveStages` -> `report.next.to`). Dann bleibt der Reiter aktiv und bietet
   * den Start an bzw. erklärt bei einem Lauf ohne Graph, warum es keinen gibt.
   */
  reportStartable?: boolean
}

export function deriveRunTabs(input: RunTabInput): RunTab[] {
  const { simulationId, projectId, latestReportId, reportStartable = false } = input
  return [
    { key: 'overview', to: { name: 'RunOverview', params: { simulationId } }, disabledReason: null },
    { key: 'graph', to: { name: 'RunGraph', params: { simulationId } }, disabledReason: null },
    projectId
      ? { key: 'personas', to: { name: 'StepEnvSetup', params: { projectId } }, disabledReason: null }
      : { key: 'personas', to: null, disabledReason: 'noProject' },
    { key: 'simulation', to: { name: 'RunSimulationFeed', params: { simulationId } }, disabledReason: null },
    // Ohne `reportId` öffnet der Reiter die jüngste Fassung bzw. den Start.
    latestReportId || reportStartable
      ? { key: 'report', to: { name: 'RunReport', params: { simulationId } }, disabledReason: null }
      : { key: 'report', to: null, disabledReason: 'noReport' },
    { key: 'interviews', to: { name: 'RunInterviews', params: { simulationId } }, disabledReason: null },
  ]
}
