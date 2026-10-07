/**
 * Zustandsableitung des Lauf-Arbeitsbereichs (Etappe 2, #1797, Bauplan 4.1/4.2).
 *
 * Rein und ohne Netzwerk: aus den bereits geladenen Jobs (RunRegistry) und
 * Berichten des Laufs entsteht je Stufe genau eine Zeile. Die Ebenen bleiben
 * getrennt (CONTEXT.md): ein Job-Status sagt nichts über den Berichtsstatus,
 * und aus einer Stufe wird nie auf die ganze Pipeline geschlossen.
 * "Unvollständig" ist ein eigener Zustand und nie "fertig".
 */

import { asRunRegistryId } from '@/contracts/runIdentifiers'
import { PENDING_REPORT_ID, REPORT_SIMULATION_ID_QUERY_KEY } from '@/utils/reportRoute'

export type StageKey = 'graph' | 'personas' | 'simulation' | 'report' | 'interviews'

export const STAGE_ORDER: readonly StageKey[] = ['graph', 'personas', 'simulation', 'report', 'interviews']

/** Stufenzustände, in denen es (noch) keine abgeschlossene Simulation gibt. */
export const NOT_FINISHED_STATES: ReadonlySet<StageStateKind> = new Set<StageStateKind>([
  'notStarted',
  'queued',
  'running',
  'paused',
])

export type StageStateKind =
  | 'notStarted'
  | 'queued'
  | 'running'
  | 'paused'
  | 'done'
  | 'degraded'
  | 'fallback'
  | 'incomplete'
  | 'stopped'
  | 'budget'
  | 'failed'
  | 'notRecorded'

/** Grund, warum eine Stufe trotz Abschluss nicht als einfach "fertig" gilt. */
export interface DegradationReason {
  /** Schlüssel unter `views.run.degradation.<code>`. */
  code: string
  /** Freitext aus dem Backend (Ursache), falls vorhanden. */
  detail?: string
  /** Zahl für Platzhalter (z. B. fehlende Abschnitte). */
  count?: number
}

export interface JobUsage {
  durationSec: number | null
  tokens: number | null
  costMicros: number | null
}

export interface JobRoute {
  providerId: string
  model: string
}

export interface JobInfo {
  runId: string
  runType: string
  status: string
  terminationReason: string | null
  startedAt: string | null
  completedAt: string | null
  updatedAt: string
  /** Rückfall ohne Routen-Snapshot: Modelle aus dem Verbrauchs-Ledger (`usage.by_model`). */
  models: string[]
  /** Beim Jobstart festgeschriebene Route (`llm-routing`-Snapshot der Stufe). */
  route?: JobRoute | null
  /** Der Snapshot ließ sich nicht laden (sichtbar, nicht als "nicht erfasst" getarnt). */
  routeLoadFailed?: boolean
  usage: JobUsage | null
  error: string | null
  /** Nur am Personas-Job gesetzt (`summary.persona_count`). */
  personaCount?: number | null
}

export interface ReportInfo {
  reportId: string
  /** Berichtsstatus (`pending|planning|generating|incomplete|completed|failed`). */
  status: string
  missingSections: number
  createdAt: string
  /** `simulation_requirement` des Berichts (die Frage des Laufs). */
  requirement?: string
  degradations: { component: string; reason: string; severity: 'warning' | 'blocking' }[]
  /** Ergebnis der Evidence-Prüfung: `omitted` entspricht `evidence_omitted`. */
  evidence: 'ok' | 'omitted' | 'failed' | 'unchecked'
}

export interface RunWorkspaceData {
  simulationId: string
  projectId: string | null
  /** Der Graph des Projekts existiert (auch wenn der Graph-Job fehlt). */
  hasGraph: boolean
  /** Neuester Job je Jobtyp. */
  jobs: Partial<Record<string, JobInfo>>
  /** Berichte der Simulation, neueste zuerst. */
  reports: ReportInfo[]
}

export type StepKind = 'start' | 'resume' | 'view'

export interface RouteTarget {
  name: string
  params: Record<string, string>
  /** Nur gesetzt, wenn das Ziel Query-Werte mitnimmt (Startparameter). */
  query?: Record<string, string>
}

export interface NextStep {
  kind: StepKind
  to: RouteTarget | null
  /** Schlüssel unter `views.run.disabled.<key>`, wenn `to` fehlt. */
  disabledReason: string | null
}

export interface StageRow {
  key: StageKey
  state: StageStateKind
  /** Terminationsgrund für die Textzeile: `process_restart`, `user_stop`, … */
  terminationReason: string | null
  degradations: DegradationReason[]
  job: JobInfo | null
  reportId: string | null
  next: NextStep
  updatedAt: string | null
}

const JOB_TYPE: Record<Exclude<StageKey, 'report' | 'interviews'>, string> = {
  graph: 'graph_build',
  personas: 'simulation_prepare',
  simulation: 'simulation_run',
}

const COMPONENT_STAGE: Record<string, StageKey> = {
  persona_generation: 'personas',
  simulation: 'simulation',
  simulation_positioning: 'simulation',
  interview_agents: 'interviews',
}

const ACTIVE = new Set(['running', 'queued', 'paused'])
export const DONE_KINDS: readonly StageStateKind[] = ['done', 'degraded', 'fallback', 'incomplete']

function kindFromJob(job: JobInfo): StageStateKind {
  const reason = job.terminationReason ?? ''
  switch (job.status) {
    case 'pending':
      return 'queued'
    case 'processing':
      return 'running'
    case 'paused':
      return 'paused'
    case 'completed':
      return 'done'
    case 'stopped':
    case 'failed':
      if (reason.startsWith('budget_')) return 'budget'
      if (reason === 'user_stop' || reason === 'user_cancel') return 'stopped'
      return job.status === 'stopped' ? 'stopped' : 'failed'
    default:
      return 'notRecorded'
  }
}

function kindFromReport(report: ReportInfo): StageStateKind {
  switch (report.status) {
    case 'pending':
    case 'planning':
    case 'generating':
      return 'running'
    case 'incomplete':
      return 'incomplete'
    case 'completed':
      return 'done'
    case 'failed':
      return 'failed'
    default:
      return 'notRecorded'
  }
}

function reportDegradations(report: ReportInfo | null): DegradationReason[] {
  if (!report) return []
  const out: DegradationReason[] = []
  if (report.missingSections > 0) out.push({ code: 'missingSections', count: report.missingSections })
  if (report.evidence === 'omitted') out.push({ code: 'evidenceOmitted' })
  if (report.evidence === 'failed') out.push({ code: 'evidenceCheckFailed' })
  return out
}

function backendDegradations(report: ReportInfo | null, stage: StageKey): DegradationReason[] {
  if (!report) return []
  return report.degradations
    .filter((d) => (COMPONENT_STAGE[d.component] ?? 'report') === stage)
    .map((d) => ({ code: d.component, detail: d.reason }))
}

function hasBlocking(report: ReportInfo | null, stage: StageKey): boolean {
  return !!report?.degradations.some((d) => d.severity === 'blocking' && (COMPONENT_STAGE[d.component] ?? 'report') === stage)
}

function target(name: string, params: Record<string, string>, query?: Record<string, string>): RouteTarget {
  return query && Object.keys(query).length > 0 ? { name, params, query } : { name, params }
}

/** Berichtsseite im Zustand „bereit, noch nicht gestartet“ (Sentinel-ID, Simulation und Lauf in der Query). */
function reportReadyTarget(data: RunWorkspaceData): RouteTarget {
  const query: Record<string, string> = { [REPORT_SIMULATION_ID_QUERY_KEY]: data.simulationId }
  const runId = asRunRegistryId(data.jobs['simulation_run']?.runId)
  if (runId) query.runId = runId
  return target('Report', { reportId: PENDING_REPORT_ID }, query)
}

function disabled(reason: string, kind: StepKind): NextStep {
  return { kind, to: null, disabledReason: reason }
}

function enabled(kind: StepKind, to: RouteTarget): NextStep {
  return { kind, to, disabledReason: null }
}

const RESUMABLE = new Set<StageStateKind>(['stopped', 'failed', 'budget', 'paused'])

function nextStepFor(
  key: StageKey,
  state: StageStateKind,
  data: RunWorkspaceData,
  reportId: string | null,
  rows: Map<StageKey, StageStateKind>,
): NextStep {
  const stepKind: StepKind =
    state === 'notStarted' ? 'start' : RESUMABLE.has(state) ? 'resume' : 'view'
  const project = data.projectId
  switch (key) {
    case 'graph':
      if (stepKind === 'view') return enabled('view', target('RunGraph', { simulationId: data.simulationId }))
      return project
        ? enabled(stepKind, target('StepGraphBuild', { projectId: project }))
        : disabled('noProject', stepKind)
    case 'personas':
      return project
        ? enabled(stepKind, target('StepEnvSetup', { projectId: project }))
        : disabled('noProject', stepKind)
    case 'simulation':
      return stepKind === 'view'
        ? enabled('view', target('RunSimulationFeed', { simulationId: data.simulationId }))
        : enabled(stepKind, target('RunSimulationFeed', { simulationId: data.simulationId }))
    case 'report': {
      if (reportId) return enabled('view', target('StepReport', { reportId }))
      const sim = rows.get('simulation') ?? 'notStarted'
      if (!DONE_KINDS.includes(sim)) return disabled('afterSimulation', 'start')
      // Der Bericht wird erst auf der Berichtsseite nach Bestätigung gestartet (#1023, #1801).
      return enabled('start', reportReadyTarget(data))
    }
    case 'interviews':
      return enabled('view', target('RunInterviews', { simulationId: data.simulationId }))
  }
}

/**
 * Je Stufe eine Zeile; die Reihenfolge entspricht `STAGE_ORDER`. Die
 * vorgemerkten Startparameter des Startdialogs liest die Steuerung der
 * Simulation selbst (`pendingRunParams`); sie reisen nicht mehr durch die Adresse.
 */
export function deriveStages(data: RunWorkspaceData): StageRow[] {
  const latestReport = data.reports[0] ?? null
  const reportJob = data.jobs['report_generate'] ?? null

  // Hat eine spätere Stufe Spuren, fehlt der Job einer früheren nur im Register.
  const hasTrace: Record<StageKey, boolean> = {
    graph: !!data.jobs['graph_build'] || data.hasGraph,
    personas: !!data.jobs['simulation_prepare'],
    simulation: !!data.jobs['simulation_run'],
    report: !!reportJob || !!latestReport,
    interviews: false,
  }
  const laterTrace = (key: StageKey): boolean =>
    STAGE_ORDER.slice(STAGE_ORDER.indexOf(key) + 1).some((k) => hasTrace[k])

  const kinds = new Map<StageKey, StageStateKind>()
  const rows: StageRow[] = []

  for (const key of STAGE_ORDER) {
    let job: JobInfo | null = null
    let state: StageStateKind = 'notStarted'
    let reportId: string | null = null

    if (key === 'interviews') {
      // Für Interviews führt das Register keinen Job: ehrlich "nicht erfasst".
      state = 'notRecorded'
    } else if (key === 'report') {
      job = reportJob
      reportId = latestReport?.reportId ?? null
      const jobKind = job ? kindFromJob(job) : null
      if (job && ACTIVE.has(jobKind as string)) state = jobKind as StageStateKind
      else if (latestReport) {
        const repKind = kindFromReport(latestReport)
        // Ein terminaler Job schlägt einen veralteten "generating"-Bericht.
        state = repKind === 'running' && jobKind && !ACTIVE.has(jobKind) ? jobKind : repKind
      } else if (jobKind) state = jobKind
    } else {
      job = data.jobs[JOB_TYPE[key]] ?? null
      if (job) state = kindFromJob(job)
      else if (laterTrace(key) || (key === 'graph' && data.hasGraph)) state = 'notRecorded'
    }

    const degradations: DegradationReason[] = []
    if (key === 'report') degradations.push(...reportDegradations(latestReport))
    degradations.push(...backendDegradations(latestReport, key))
    if (state === 'done' && key === 'personas' && degradations.some((d) => d.code === 'persona_generation')) {
      state = 'fallback'
    } else if (state === 'done' && degradations.length > 0) {
      const incomplete = key === 'report' && (degradations.some((d) => d.code === 'missingSections') || hasBlocking(latestReport, key))
      state = incomplete ? 'incomplete' : 'degraded'
    }
    if (key === 'report' && state === 'incomplete' && degradations.length === 0 && latestReport?.status === 'incomplete') {
      degradations.push({ code: 'reportIncomplete' })
    }

    kinds.set(key, state)
    const updatedAt =
      key === 'report' ? (job?.updatedAt ?? latestReport?.createdAt ?? null) : (job?.updatedAt ?? null)
    rows.push({
      key,
      state,
      terminationReason: job?.terminationReason ?? null,
      degradations,
      job,
      reportId,
      next: nextStepFor(key, state, data, reportId, kinds),
      updatedAt,
    })
  }
  return rows
}

/**
 * Kopfmarke des Laufs: der Zustand der zuletzt bewegten Stufe, mit Nennung der
 * Stufe. Läuft eine Stufe, gewinnt sie. Kein Schluss auf die ganze Pipeline.
 */
export function deriveHeadline(rows: StageRow[]): { stage: StageKey; state: StageStateKind } | null {
  const active = rows.find((r) => r.state === 'running' || r.state === 'queued')
  if (active) return { stage: active.key, state: active.state }
  let best: StageRow | null = null
  for (const r of rows) {
    if (!r.updatedAt || r.state === 'notStarted' || r.state === 'notRecorded') continue
    if (!best || (r.updatedAt >= (best.updatedAt ?? ''))) best = r
  }
  return best ? { stage: best.key, state: best.state } : null
}

/** Dauer eines Jobs in Sekunden: Wanduhr aus Start/Ende, sonst nicht erfasst. */
export function wallClockSeconds(job: Pick<JobInfo, 'startedAt' | 'completedAt'>): number | null {
  if (!job.startedAt || !job.completedAt) return null
  const ms = Date.parse(job.completedAt) - Date.parse(job.startedAt)
  return Number.isFinite(ms) && ms >= 0 ? Math.round(ms / 1000) : null
}
