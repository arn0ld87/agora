/**
 * Zustand und Zeilenmodell eines Jobs der `RunRegistry` (Aktivität, #1797).
 *
 * Ein Job ist ein einzelner Schritt (Graph-Build, Ontologie, Prepare,
 * Simulation, Report); im Code heißt er weiter `run_id`/`run_type`. Der Lauf
 * ist das ganze Vorhaben und wird über `linked_ids.simulation_id` erreicht.
 *
 * Die Zustände bleiben getrennt: gestoppt (Nutzer), Budget erschöpft und
 * fehlgeschlagen (auch `process_restart`) werden nie zusammengelegt.
 */
import type { RunDetail } from '../../contracts/runsContract'
import { TerminationReasonSchema, type TerminationReason } from '../../contracts/runBudgetContract'

export const JOB_STATES = [
  'pending',
  'running',
  'paused',
  'completed',
  'stopped',
  'budget',
  'failed',
] as const
export type JobState = (typeof JOB_STATES)[number]

/** Glyphe je Zustand: der Zustand hängt nie nur an der Farbe. */
export const JOB_STATE_GLYPH: Record<JobState, string> = {
  pending: '○',
  running: '◔',
  paused: '❙❙',
  completed: '✓',
  stopped: '■',
  budget: '€',
  failed: '✕',
}

/** Jobarten, für die `POST /api/runs/<id>/cancel` einen Abbruch auswertet. */
const CANCELLABLE_RUN_TYPES = new Set([
  'graph_build',
  'simulation_prepare',
  'simulation_run',
  'report_generate',
  'report_generation',
])

/** `termination_reason` steht je nach Endpunkt am Job selbst oder in dessen `metadata`. */
export function terminationReasonOf(run: RunDetail): TerminationReason | null {
  const top = (run as { termination_reason?: unknown }).termination_reason
  const raw = typeof top === 'string' && top ? top : run.metadata?.['termination_reason']
  const parsed = TerminationReasonSchema.safeParse(raw)
  return parsed.success ? parsed.data : null
}

export function jobStateOf(run: RunDetail): JobState {
  const reason = terminationReasonOf(run)
  const terminal = run.status === 'completed' || run.status === 'failed' || run.status === 'stopped'
  if (terminal && reason) {
    if (reason.startsWith('budget_')) return 'budget'
    if (reason === 'process_restart') return 'failed'
    if (reason === 'user_stop' || reason === 'user_cancel') return 'stopped'
  }
  switch (run.status) {
    case 'pending':
      return 'pending'
    case 'processing':
      return 'running'
    case 'paused':
      return 'paused'
    case 'completed':
      return 'completed'
    case 'stopped':
      return 'stopped'
    case 'failed':
      return 'failed'
  }
}

function linkedString(run: RunDetail, key: string): string | null {
  const v = run.linked_ids?.[key]
  return typeof v === 'string' && v ? v : null
}

export interface JobRow {
  runId: string
  runType: string
  state: JobState
  reason: TerminationReason | null
  /** Simulationskennung des Laufs; nur gesetzt, wenn der Job eine Simulation trägt. */
  simulationId: string | null
  /** Anzeigename des Laufs, soweit der Job einen kennt. */
  runLabel: string | null
  progress: number
  message: string
  startedAt: string
  durationMs: number | null
  cancellable: boolean
}

export function jobRowOf(run: RunDetail, now: number): JobRow {
  const state = jobStateOf(run)
  const started = Date.parse(run.started_at)
  const endIso = run.completed_at ?? (state === 'running' || state === 'pending' ? null : run.updated_at)
  const end = endIso ? Date.parse(endIso) : now
  const durationMs = Number.isFinite(started) && Number.isFinite(end) ? Math.max(0, end - started) : null
  return {
    runId: run.run_id,
    runType: run.run_type,
    state,
    reason: terminationReasonOf(run),
    simulationId: linkedString(run, 'simulation_id'),
    runLabel: run.summary?.document_name ?? run.summary?.graph_name ?? null,
    progress: run.progress,
    message: run.message,
    startedAt: run.started_at,
    durationMs,
    // Abbrechen nur laufende (bei `pending` beendet der Server den Job direkt).
    cancellable: (state === 'running' || state === 'pending') && CANCELLABLE_RUN_TYPES.has(run.run_type),
  }
}

/** Neueste zuerst, wie die Jobliste der Ablage. */
export function jobRowsOf(runs: readonly RunDetail[], now: number): JobRow[] {
  return [...runs]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .map((r) => jobRowOf(r, now))
}

export interface JobFilter {
  kind: string
  state: JobState | ''
}

export function filterJobRows(rows: readonly JobRow[], f: JobFilter): JobRow[] {
  return rows.filter((r) => (!f.kind || r.runType === f.kind) && (!f.state || r.state === f.state))
}

/** `3 min 31 s`, `8 s`, `1 h 4 min`; `—` ohne Wert. */
export function formatDuration(ms: number | null): string {
  if (ms === null) return '—'
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return m > 0 ? `${h} h ${m} min` : `${h} h`
  if (m > 0) return s > 0 ? `${m} min ${s} s` : `${m} min`
  return `${s} s`
}
