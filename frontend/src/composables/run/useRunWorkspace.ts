/**
 * Lädt die Daten des Lauf-Arbeitsbereichs (Etappe 2, #1797) und stellt sie
 * Arbeitsbereich und Übersicht gemeinsam bereit. Nur bestehende Endpunkte;
 * jede Antwort läuft durch ein Zod-Schema (`safeParse`). Schlägt ein
 * Pflichtteil fehl, steht ein sichtbarer Fehler da, nichts wird still
 * ausgelassen. Optionale Teile (Verbrauch, Evidence-Prüfung) benennen ihren
 * Ausfall in den Daten.
 */
import { computed, inject, ref, type ComputedRef, type InjectionKey, type Ref } from 'vue'
import { z } from 'zod'
import { getSimulation } from '@/api/simulation'
import { getProject } from '@/api/graph'
import { getRun, listRuns } from '@/api/runs'
import { getRunLlmRouting } from '@/api/llmRouting'
import { getReportEvidence, listReports } from '@/api/report'
import { RunDetailSchema, RunsListResponseSchema } from '@/contracts/runsContract'
import { RunUsageSchema, TerminationReasonSchema, type RunUsage } from '@/contracts/runBudgetContract'
import { ReportSchema } from '@/contracts/reportContract'
import { ProjectSchema } from '@/contracts/projectContract'
import { ApiError } from '@/api/envelope'
import {
  deriveHeadline,
  deriveStages,
  type JobInfo,
  type JobRoute,
  type ReportInfo,
  type RunWorkspaceData,
  type StageRow,
} from './runStageState'
import { deriveRunTabs, type RunTab } from './runTabs'

const SimulationLookupSchema = z
  .object({
    simulation_id: z.string().min(1),
    project_id: z.string().nullable().optional(),
    status: z.string().optional(),
  })
  .passthrough()

/** `GET /api/runs/<id>`: Run-Detail samt Verbrauch und Abbruchgrund (#764). */
const RunJobDetailSchema = RunDetailSchema.extend({
  usage: RunUsageSchema.nullable().optional(),
  termination_reason: TerminationReasonSchema.nullable().optional(),
})

export type LoadState = 'loading' | 'ready' | 'notFound' | 'error'

export type RunUsageInfo = RunUsage

export interface RunWorkspace {
  state: Ref<LoadState>
  /** Fehlertext des letzten Ladeversuchs (Transport oder Vertragsbruch). */
  error: Ref<string | null>
  data: Ref<RunWorkspaceData | null>
  /** Die Frage des Laufs (`simulation_requirement` des Projekts), falls erfasst. */
  question: Ref<string | null>
  graphName: Ref<string | null>
  personaCount: ComputedRef<number | null>
  stages: ComputedRef<StageRow[]>
  headline: ComputedRef<ReturnType<typeof deriveHeadline>>
  tabs: ComputedRef<RunTab[]>
  /** Job, dessen Budget die Übersicht zeigt (Simulation, sonst der jüngste). */
  budgetJob: ComputedRef<JobInfo | null>
  reload: () => Promise<void>
}

export const RUN_WORKSPACE_KEY: InjectionKey<RunWorkspace> = Symbol('run-workspace')

export function useRunWorkspaceContext(): RunWorkspace {
  const ws = inject(RUN_WORKSPACE_KEY, null)
  if (!ws) throw new Error('useRunWorkspaceContext braucht RunWorkspaceView als Elternansicht')
  return ws
}

function describe(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return String(err)
}

function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

function usageOf(usage: RunUsage | null | undefined): JobInfo['usage'] {
  if (!usage) return null
  const t = usage.totals
  return {
    durationSec: t.duration_ms > 0 ? Math.round(t.duration_ms / 1000) : null,
    tokens: t.total_tokens ?? null,
    costMicros: t.cost_micros ?? null,
  }
}

/**
 * Rückfall ohne Routen-Snapshot. `summary.model` zählt bewusst nicht: es ist das
 * Modell der Simulationskonfiguration und stünde bei Prepare, Simulation und
 * Bericht gleich da.
 */
function modelsOf(usage: RunUsage | null | undefined): string[] {
  return usage ? Object.keys(usage.by_model) : []
}

/** Stufenschlüssel des `llm-routing`-Snapshots je Jobtyp. */
const SNAPSHOT_STAGE: Record<string, string> = {
  graph_build: 'graph_build',
  simulation_prepare: 'persona_generation',
  simulation_run: 'simulation_rounds',
  report_generate: 'report_generation',
}

const SnapshotRouteSchema = z.object({ provider_id: z.string(), model: z.string() }).passthrough()
const RunRoutingSchema = z.object({ snapshots: z.record(z.string(), z.unknown()) }).passthrough()

/** Route der Stufe aus dem Snapshot; `failed` nur bei Lade-/Vertragsfehler, nicht bei fehlendem Eintrag. */
async function loadRoute(job: JobInfo): Promise<Pick<JobInfo, 'route' | 'routeLoadFailed'>> {
  const stage = SNAPSHOT_STAGE[job.runType]
  if (!stage) return { route: null, routeLoadFailed: false }
  try {
    const res = RunRoutingSchema.safeParse(await getRunLlmRouting(job.runId))
    if (!res.success) throw new Error(`Vertragsbruch GET /api/runs/${job.runId}/llm-routing: ${res.error.message}`)
    const entry = res.data.snapshots[stage]
    if (entry === undefined || entry === null) return { route: null, routeLoadFailed: false }
    const route = SnapshotRouteSchema.safeParse(entry)
    if (!route.success) throw new Error(`Vertragsbruch Snapshot ${stage}: ${route.error.message}`)
    const value: JobRoute = { providerId: route.data.provider_id, model: route.data.model }
    return { route: value, routeLoadFailed: false }
  } catch (err) {
    console.warn('[run-workspace] llm-routing-Snapshot nicht ladbar', { runId: job.runId, stage, error: describe(err) })
    return { route: null, routeLoadFailed: true }
  }
}

function terminationOf(run: z.infer<typeof RunJobDetailSchema>): string | null {
  if (run.termination_reason) return run.termination_reason
  const meta = run.metadata['termination_reason']
  return typeof meta === 'string' && meta ? meta : null
}

function toJob(run: z.infer<typeof RunJobDetailSchema>): JobInfo {
  return {
    runId: run.run_id,
    runType: run.run_type,
    status: run.status,
    terminationReason: terminationOf(run),
    startedAt: run.started_at,
    completedAt: run.completed_at ?? null,
    updatedAt: run.updated_at,
    models: modelsOf(run.usage),
    usage: usageOf(run.usage),
    error: run.error ?? null,
    personaCount: run.summary?.persona_count ?? null,
  }
}

async function loadJobs(simulationId: string): Promise<JobInfo[]> {
  const res = await listRuns({ simulation_id: simulationId, limit: 100 })
  if (!res?.success) throw new Error(res?.error || res?.message || 'listRuns')
  const parsed = RunsListResponseSchema.safeParse(res.data)
  if (!parsed.success) throw new Error(`Vertragsbruch GET /api/runs: ${parsed.error.message}`)

  // Neuester Job je Jobtyp; für diesen nachladen, weil nur das Detail den Verbrauch trägt.
  const newest = new Map<string, z.infer<typeof RunDetailSchema>>()
  for (const run of parsed.data.runs) {
    const cur = newest.get(run.run_type)
    if (!cur || run.updated_at > cur.updated_at) newest.set(run.run_type, run)
  }
  const jobs: JobInfo[] = []
  for (const run of newest.values()) {
    let detail: z.infer<typeof RunJobDetailSchema> | null = null
    try {
      const r = await getRun(run.run_id)
      const p = r?.success ? RunJobDetailSchema.safeParse(r.data) : null
      detail = p?.success ? p.data : null
    } catch {
      detail = null
    }
    // Ohne lesbares Detail zeigt die Zeile den Job ohne Verbrauch ("nicht erfasst").
    jobs.push(toJob(detail ?? { ...run, usage: null, termination_reason: null }))
  }
  // Je Stufe parallel und fehlertolerant: ein Ausfall betrifft nur diese Zeile.
  return Promise.all(jobs.map(async (job) => ({ ...job, ...(await loadRoute(job)) })))
}

async function loadReports(simulationId: string): Promise<ReportInfo[]> {
  const res = await listReports({ simulation_id: simulationId, limit: 50 })
  const env = res as unknown as { success?: boolean; data?: unknown; error?: string }
  if (!env?.success) throw new Error(env?.error || 'listReports')
  const parsed = z.array(ReportSchema).safeParse(env.data)
  if (!parsed.success) throw new Error(`Vertragsbruch GET /api/report/list: ${parsed.error.message}`)
  const sorted = [...parsed.data].sort((a, b) =>
    (b.completed_at || b.created_at || '').localeCompare(a.completed_at || a.created_at || ''),
  )
  const infos: ReportInfo[] = sorted.map((r) => ({
    reportId: r.report_id,
    status: r.status,
    missingSections: r.missing_sections.length,
    createdAt: r.completed_at || r.created_at || '',
    requirement: r.simulation_requirement,
    degradations: r.run_degradations.map((d) => ({ component: d.component, reason: d.reason, severity: d.severity })),
    evidence: 'unchecked',
  }))
  const latest = infos[0]
  if (latest) {
    try {
      const ev = await getReportEvidence(latest.reportId)
      if ('evidence_omitted' in ev && ev.evidence_omitted) latest.evidence = 'omitted'
      else latest.evidence = ev.success === true ? 'ok' : 'failed'
    } catch {
      latest.evidence = 'failed'
    }
  }
  return infos
}

export function useRunWorkspace(simulationId: () => string): RunWorkspace {
  const state = ref<LoadState>('loading')
  const error = ref<string | null>(null)
  const data = ref<RunWorkspaceData | null>(null)
  const question = ref<string | null>(null)
  const graphName = ref<string | null>(null)
  let token = 0

  async function reload(): Promise<void> {
    const id = simulationId()
    const mine = ++token
    state.value = 'loading'
    error.value = null
    try {
      const simRes = await getSimulation(id)
      if (mine !== token) return
      if (!simRes?.success) {
        if (typeof simRes?.code === 'string' && simRes.code.includes('not_found')) {
          data.value = null
          state.value = 'notFound'
          return
        }
        throw new Error(typeof simRes?.error === 'string' && simRes.error ? simRes.error : 'getSimulation')
      }
      const sim = SimulationLookupSchema.safeParse(simRes.data)
      if (!sim.success) throw new Error(`Vertragsbruch GET /api/simulation/${id}: ${sim.error.message}`)
      const projectId = sim.data.project_id || null

      let hasGraph = false
      question.value = null
      graphName.value = null
      if (projectId) {
        try {
          const pr = await getProject(projectId)
          const pp = pr?.success ? ProjectSchema.safeParse(pr.data) : null
          if (pp?.success) {
            question.value = pp.data.simulation_requirement?.trim() || null
            graphName.value = pp.data.name || null
            hasGraph = !!pp.data.graph_id
          }
        } catch {
          // Die Frage ist Zusatz; sie fehlt dann sichtbar ("nicht erfasst").
        }
      }

      const [jobs, reports] = await Promise.all([loadJobs(id), loadReports(id)])
      if (mine !== token) return

      // Zweite Quelle für die Frage: der Bericht trägt sie mit.
      if (!question.value) question.value = reports[0]?.requirement?.trim() || null
      const byType: Record<string, JobInfo> = {}
      for (const j of jobs) byType[j.runType] = j
      data.value = { simulationId: id, projectId, hasGraph, jobs: byType, reports }
      state.value = 'ready'
    } catch (err) {
      if (mine !== token) return
      data.value = null
      if (isNotFound(err)) {
        state.value = 'notFound'
      } else {
        state.value = 'error'
        error.value = describe(err)
      }
    }
  }

  const stages = computed(() => (data.value ? deriveStages(data.value) : []))
  const headline = computed(() => deriveHeadline(stages.value))
  const tabs = computed(() =>
    deriveRunTabs({
      simulationId: simulationId(),
      projectId: data.value?.projectId ?? null,
      latestReportId: data.value?.reports[0]?.reportId ?? null,
    }),
  )
  const budgetJob = computed<JobInfo | null>(() => {
    const jobs = data.value?.jobs
    if (!jobs) return null
    const sim = jobs['simulation_run']
    if (sim) return sim
    return Object.values(jobs).reduce<JobInfo | null>(
      (best, j) => (j && (!best || j.updatedAt > best.updatedAt) ? j : best),
      null,
    )
  })

  const personaCount = computed<number | null>(() => {
    const n = data.value?.jobs['simulation_prepare']?.personaCount
    return typeof n === 'number' ? n : null
  })

  return { state, error, data, question, graphName, personaCount, stages, headline, tabs, budgetJob, reload }
}
