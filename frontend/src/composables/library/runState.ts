import { ATTENTION_REPORT_STATUS, ATTENTION_STATUSES, RUNNING_STATUSES } from '../useLibraryCounts'
import type { ShelfLaufJob, ShelfObject } from '../../types/shelf'

/**
 * Reine Ableitungen der Bibliothek der Laeufe (#1797, Bauplan 4.1).
 *
 * Die Zustaende eines Laufs werden nie zusammengelegt (CONTEXT.md): laeuft,
 * fertig, unvollstaendig (`INCOMPLETE`), gestoppt (`user_stop`), Budget
 * erschoepft, fehlgeschlagen (auch `process_restart`). „Unvollstaendig“ teilt
 * sich weder Farbe noch Symbol mit „fertig“. Zusaetzlich kennt die Ableitung
 * „pausiert“ (Job-Status `paused`), weil ein pausierter Lauf weder laeuft noch
 * gestoppt ist.
 *
 * Alles hier nutzt nur, was der Ablage-Stand (`ShelfObject`) wirklich traegt.
 * Fehlt eine Angabe (Kosten, Runde, Modell je Fassung), gibt es kein Feld.
 */

/** Zustand eines Laufs oder einer Stufe. `pending`/`unknown` gibt es nur bei Stufen. */
export type LibraryState =
  | 'running'
  | 'paused'
  | 'done'
  | 'incomplete'
  | 'stopped'
  | 'budget'
  | 'failed'
  | 'pending'
  | 'unknown'

/** Zeichen je Zustand: der Zustand steht nie nur in der Farbe. `running` zeigt einen Spinner. */
export const STATE_GLYPH: Record<LibraryState, string> = {
  running: '',
  paused: '‖',
  done: '✓',
  incomplete: '◐',
  stopped: '■',
  budget: '€',
  failed: '✕',
  pending: '○',
  unknown: '–',
}

export type StageKey = 'graph' | 'personas' | 'simulation' | 'report' | 'interviews'

export interface StageEntry {
  key: StageKey
  state: LibraryState
}

export type RunsView = 'all' | 'running' | 'attention' | 'with-report'

export const RUNS_VIEWS: readonly RunsView[] = ['all', 'running', 'attention', 'with-report']

/** `?view=` -> Ansicht; alles Unbekannte faellt auf „alle“ (kaputte Deep-Links duerfen nichts sprengen). */
export function parseRunsView(raw: unknown): RunsView {
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' && (RUNS_VIEWS as readonly string[]).includes(value) && value !== 'all'
    ? (value as RunsView)
    : 'all'
}

const BUDGET_REASON_PREFIX = 'budget_'

function isBudget(job: ShelfLaufJob | undefined): boolean {
  return Boolean(job?.terminationReason?.startsWith(BUDGET_REASON_PREFIX))
}

/** Bericht-Status (ReportStatusSchema) -> Zustand. `incomplete` ist nie `done`. */
export function reportStatusState(status: string | null | undefined): LibraryState {
  switch (status) {
    case 'completed':
      return 'done'
    case 'incomplete':
      return 'incomplete'
    case 'failed':
      return 'failed'
    case 'pending':
    case 'planning':
    case 'generating':
      return 'running'
    default:
      return 'unknown'
  }
}

/** Zustand eines einzelnen Jobs. */
export function jobState(job: ShelfLaufJob): LibraryState {
  switch (job.status) {
    case 'pending':
      return 'pending'
    case 'processing':
      return 'running'
    case 'paused':
      return 'paused'
    case 'completed':
      return 'done'
    case 'failed':
      return isBudget(job) ? 'budget' : 'failed'
    case 'stopped':
      return isBudget(job) ? 'budget' : 'stopped'
    default:
      return 'unknown'
  }
}

/** Simulationskennungen eines Laufs: der Schluessel selbst (meist `sim_…`) und alle Job-Verknuepfungen. */
export function simulationIdsOf(lauf: ShelfObject): string[] {
  const ids = new Set<string>([lauf.id])
  for (const job of lauf.jobs ?? []) {
    const sim = job.linkedIds.simulation_id
    if (typeof sim === 'string' && sim) ids.add(sim)
  }
  return [...ids]
}

/** Simulation, auf die „Lauf oeffnen“ und „Vergleichen“ zeigen; `null`, wenn der Lauf keine hat. */
export function primarySimulationId(lauf: ShelfObject): string | null {
  for (const job of lauf.jobs ?? []) {
    const sim = job.linkedIds.simulation_id
    if (typeof sim === 'string' && sim) return sim
  }
  return lauf.id.startsWith('sim_') ? lauf.id : null
}

/** Berichte eines Laufs, juengster zuerst. */
export function reportsOfLauf(lauf: ShelfObject, bySimulation: Map<string, ShelfObject[]>): ShelfObject[] {
  const seen = new Set<string>()
  const result: ShelfObject[] = []
  for (const sim of simulationIdsOf(lauf)) {
    for (const report of bySimulation.get(sim) ?? []) {
      if (seen.has(report.id)) continue
      seen.add(report.id)
      result.push(report)
    }
  }
  return result.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export function indexReportsBySimulation(objects: ShelfObject[]): Map<string, ShelfObject[]> {
  const map = new Map<string, ShelfObject[]>()
  for (const o of objects) {
    if (o.kind !== 'bericht' || !o.simulationId) continue
    const list = map.get(o.simulationId)
    if (list) list.push(o)
    else map.set(o.simulationId, [o])
  }
  return map
}

export function isRunning(lauf: ShelfObject): boolean {
  const status = lauf.jobs?.[0]?.status
  return status !== undefined && RUNNING_STATUSES.includes(status)
}

/**
 * „Braucht dich“ — dieselbe Regel wie der Zaehler der Seitenleiste
 * (`deriveLibraryCounts().brauchtDich`): juengster Job gestoppt oder
 * fehlgeschlagen, Budget erschoepft oder mindestens ein unvollstaendiger Bericht.
 */
export function needsAttention(lauf: ShelfObject, reports: ShelfObject[]): boolean {
  const latest = lauf.jobs?.[0]
  if (latest && ATTENTION_STATUSES.includes(latest.status)) return true
  if (isBudget(latest)) return true
  return reports.some((r) => r.reportStatus === ATTENTION_REPORT_STATUS)
}

/**
 * Zustand des Laufs: laeuft > Budget > fehlgeschlagen > gestoppt >
 * unvollstaendig > pausiert > fertig. Ein Lauf ohne Job-Angabe ist `unknown`.
 */
export function deriveRunState(lauf: ShelfObject, reports: ShelfObject[]): LibraryState {
  const latest = lauf.jobs?.[0]
  if (!latest) return 'unknown'
  if (RUNNING_STATUSES.includes(latest.status)) return 'running'
  const own = jobState(latest)
  if (own === 'budget' || own === 'failed' || own === 'stopped') return own
  if (reports.some((r) => r.reportStatus === ATTENTION_REPORT_STATUS)) return 'incomplete'
  if (own === 'paused') return 'paused'
  return own
}

const STAGE_RUN_TYPES: Record<Exclude<StageKey, 'report' | 'interviews'>, readonly string[]> = {
  graph: ['graph_build', 'ontology_generate'],
  personas: ['simulation_prepare'],
  simulation: ['simulation_run'],
}

function newestJob(lauf: ShelfObject, match: (runType: string) => boolean): ShelfLaufJob | undefined {
  return (lauf.jobs ?? []).find((j) => match(j.runType))
}

/**
 * Fuenf Stufenpunkte. Interviews erscheinen nur, wenn die Registry einen
 * Interview-Job fuehrt; sonst traegt der Stand dazu keine Angabe. Eine Stufe
 * ohne Job, hinter der eine spaetere Stufe Daten hat, ist `unknown`
 * („keine Angabe“), eine Stufe am Ende der Kette `pending` („offen“).
 */
export function deriveStages(lauf: ShelfObject, reports: ShelfObject[]): StageEntry[] {
  const raw: Array<{ key: StageKey; state: LibraryState | null }> = []
  for (const key of ['graph', 'personas', 'simulation'] as const) {
    const job = newestJob(lauf, (rt) => STAGE_RUN_TYPES[key].includes(rt))
    raw.push({ key, state: job ? jobState(job) : null })
  }
  const reportJob = newestJob(lauf, (rt) => rt === 'report_generate')
  const latestReport = reports[0]
  raw.push({
    key: 'report',
    state: latestReport ? reportStatusState(latestReport.reportStatus) : reportJob ? jobState(reportJob) : null,
  })
  const interviewJob = newestJob(lauf, (rt) => rt.includes('interview'))
  if (interviewJob) raw.push({ key: 'interviews', state: jobState(interviewJob) })

  let lastWithData = -1
  raw.forEach((s, i) => {
    if (s.state !== null) lastWithData = i
  })
  return raw.map((s, i) => ({
    key: s.key,
    state: s.state ?? (i < lastWithData ? 'unknown' : 'pending'),
  }))
}

/** Grund in einem Satz: Code fuer i18n, plus Rohtext des Jobs, falls vorhanden. */
export interface RunReason {
  code: 'user_stop' | 'process_restart' | 'budget' | 'failed' | 'stopped' | 'incomplete'
  /** Vollstaendiger Beendigungsgrund (z. B. `budget_tokens`). */
  detail?: string
  /** Statusmeldung des juengsten Jobs. */
  job?: ShelfLaufJob
}

export function deriveRunReason(lauf: ShelfObject, state: LibraryState): RunReason | null {
  const latest = lauf.jobs?.[0]
  const reason = latest?.terminationReason ?? undefined
  switch (state) {
    case 'budget':
      return { code: 'budget', detail: reason, job: latest }
    case 'stopped':
      return { code: reason === 'user_stop' ? 'user_stop' : 'stopped', detail: reason, job: latest }
    case 'failed':
      return { code: reason === 'process_restart' ? 'process_restart' : 'failed', detail: reason, job: latest }
    case 'incomplete':
      return { code: 'incomplete' }
    default:
      return null
  }
}

export interface RunEntry {
  lauf: ShelfObject
  state: LibraryState
  running: boolean
  attention: boolean
  /** Berichte des Laufs, juengster zuerst. */
  reports: ShelfObject[]
  stages: StageEntry[]
  reason: RunReason | null
  simulationId: string | null
  /** Frage des Laufs (Anforderung des juengsten Berichts); `null`, wenn kein Bericht sie traegt. */
  question: string | null
  /** Titel der Kachel: die Frage, sonst Dokument-/Graphname, sonst die Kennung. */
  title: string
  /** Quelle bzw. Graph, nur wenn der Titel die Frage ist und der Lauf einen Namen traegt. */
  source: string | null
}

export function buildRunEntries(objects: ShelfObject[]): RunEntry[] {
  const bySimulation = indexReportsBySimulation(objects)
  return objects
    .filter((o) => o.kind === 'lauf')
    .map((lauf) => {
      const reports = reportsOfLauf(lauf, bySimulation)
      const state = deriveRunState(lauf, reports)
      const latestReport = reports[0]
      const question = latestReport && latestReport.title && latestReport.title !== latestReport.id ? latestReport.title : null
      return {
        lauf,
        state,
        running: isRunning(lauf),
        attention: needsAttention(lauf, reports),
        reports,
        stages: deriveStages(lauf, reports),
        reason: deriveRunReason(lauf, state),
        simulationId: primarySimulationId(lauf),
        question,
        title: question ?? lauf.title,
        source: question && lauf.title !== lauf.id ? lauf.title : null,
      }
    })
}

/** Ziel eines Laufs: Uebersicht (`RunOverview`); ohne Simulation die Weiter-Aktion der Ablage, sonst keins. */
export function entryTarget(entry: RunEntry): { name: string; params?: Record<string, string> } | null {
  if (entry.simulationId) return { name: 'RunOverview', params: { simulationId: entry.simulationId } }
  return entry.lauf.nextAction?.to ?? null
}

export function filterRuns(entries: RunEntry[], view: RunsView): RunEntry[] {
  switch (view) {
    case 'running':
      return entries.filter((e) => e.running)
    case 'attention':
      return entries.filter((e) => e.attention)
    case 'with-report':
      return entries.filter((e) => e.reports.length > 0)
    default:
      return entries
  }
}
