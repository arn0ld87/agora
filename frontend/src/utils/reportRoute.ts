import type { RouteLocationRaw } from 'vue-router'

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
