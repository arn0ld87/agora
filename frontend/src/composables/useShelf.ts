import { computed, ref } from 'vue'
import { listRuns } from '../api/runs'
import { listReports } from '../api/report'
import { listProjects } from '../api/graph'
import { listPersonaTemplates, type PersonaTemplateRecord } from '../api/simulation'
import type { RunDetail } from '../contracts/runsContract'
import type { Report } from '../contracts/reportContract'
import type { ProjectResponse } from '../api/graph'
import type { NextAction, ShelfFilter, ShelfJobRow, ShelfObject } from '../types/shelf'

type Translate = (key: string, values?: Record<string, unknown>) => string

/**
 * Datenschicht der Ablage (Block B3).
 *
 * Aggregiert vier bestehende Quellen zu Ablage-Objekten:
 *   - RunRegistry (Jobs)             → Lauf-Zeilen, gruppiert
 *   - GET /api/report/list           → Bericht-Zeilen
 *   - GET /api/graph/project/list    → Graph-Zeilen (nur ohne Lauf)
 *   - persona-library                → Personasatz-Zeilen
 *
 * Gruppierungsregel (Q19): Ein LAUF ist das ganze Vorhaben. Jobs
 * werden ueber linked_ids.simulation_id (bevorzugt) bzw.
 * linked_ids.project_id zu einem Lauf zusammengefasst; die Zeile
 * zeigt den Zustand des juengsten Jobs. Die Rohebene bleibt ueber
 * den Filter „Alle Jobs“ erreichbar.
 */

function linkedString(run: RunDetail, key: string): string | null {
  const v = (run.linked_ids as Record<string, unknown>)[key]
  return typeof v === 'string' && v ? v : null
}

/** Vorhaben-Schluessel eines Jobs: sim_ vor proj_, sonst eigene run_id. */
export function endeavorKey(run: RunDetail): string {
  return (
    linkedString(run, 'simulation_id') ??
    linkedString(run, 'project_id') ??
    run.run_id
  )
}

/**
 * Gruppiert Jobs transitiv zu Vorhaben.
 *
 * Ein Schluessel je Job reicht NICHT: `graph_build` traegt nur eine
 * project_id, das nachfolgende `simulation_prepare` traegt project_id
 * UND simulation_id. Wuerde man je Job stur die simulation_id
 * bevorzugen, fielen genau diese beiden Jobs in verschiedene Gruppen —
 * ein und derselbe Lauf staende zweimal in der Ablage, einmal als
 * Projekt- und einmal als Simulationszeile. Das widerspricht dem
 * Glossar (CONTEXT.md): ein Lauf ist das ganze Vorhaben, eine Zeile.
 *
 * Deshalb verbinden wir alle IDs eines Jobs miteinander (Union-Find)
 * und lesen die Gruppe erst danach ab.
 */
export function groupJobsByEndeavor(runs: RunDetail[]): Map<string, RunDetail[]> {
  const parent = new Map<string, string>()

  function find(x: string): string {
    let root = x
    while (parent.get(root) !== undefined && parent.get(root) !== root) {
      root = parent.get(root) as string
    }
    // Pfadverkuerzung
    let cur = x
    while (parent.get(cur) !== undefined && parent.get(cur) !== root) {
      const next = parent.get(cur) as string
      parent.set(cur, root)
      cur = next
    }
    return root
  }

  function union(a: string, b: string): void {
    if (!parent.has(a)) parent.set(a, a)
    if (!parent.has(b)) parent.set(b, b)
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) parent.set(rb, ra)
  }

  // 1. Alle IDs eines Jobs gehoeren zusammen.
  for (const run of runs) {
    const ids = [
      linkedString(run, 'simulation_id'),
      linkedString(run, 'project_id'),
      run.run_id,
    ].filter((v): v is string => v !== null)
    if (!parent.has(ids[0])) parent.set(ids[0], ids[0])
    for (let i = 1; i < ids.length; i += 1) union(ids[0], ids[i])
  }

  // 2. Jobs ihrer Wurzel zuordnen. Als Gruppenschluessel dient die
  //    fachlich sprechendste ID des juengsten Jobs, nicht die zufaellige
  //    Union-Wurzel — sonst haengt die URL an einer Interna.
  const byRoot = new Map<string, RunDetail[]>()
  for (const run of runs) {
    const root = find(endeavorKey(run))
    const list = byRoot.get(root)
    if (list) list.push(run)
    else byRoot.set(root, [run])
  }

  const result = new Map<string, RunDetail[]>()
  for (const jobs of byRoot.values()) {
    const sorted = [...jobs].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    const latest = sorted[0]
    const key =
      linkedString(latest, 'simulation_id') ??
      linkedString(latest, 'project_id') ??
      latest.run_id
    result.set(key, sorted)
  }
  return result
}

/**
 * Uebersetzt einen dynamisch gebildeten Statusschluessel.
 *
 * vue-i18n gibt bei einem fehlenden Schluessel den SCHLUESSEL selbst
 * zurueck — ein `{ fallback }`-Argument existiert nicht, es wuerde nur
 * in eine gefundene Message interpoliert. Ohne diese Pruefung stuende
 * bei einem Status, den die Locales (noch) nicht kennen, woertlich
 * „shelf.status.report_xyz“ in der Ablage. Backend-Enums wachsen
 * schneller als Uebersetzungen, deshalb faellt der Rohwert durch.
 */
export function statusText(t: Translate, key: string, raw: string): string {
  const translated = t(key)
  return translated === key ? raw : translated
}

/**
 * Meta-Datum einer Zeile (Block B3, Redesign PR 3: „Datum bei aelteren
 * Objekten"). Heute → Uhrzeit, gestern → das Wort „Gestern"/„Yesterday",
 * sonst tt.mm. — sonst verschwimmen mehrtaegige Ablagen zu reiner
 * Uhrzeit ohne erkennbares Datum (Audit-Befund #6).
 */
export function formatShelfDate(iso: string, locale: string, t: Translate): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const now = new Date()
  const startOfDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86_400_000)
  if (diffDays === 0) return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1) return t('views.shelf.dateYesterday')
  return d.toLocaleDateString(locale, { day: '2-digit', month: '2-digit' })
}

const ACTIVE_STATUSES = new Set(['pending', 'processing', 'paused'])

function newestFirst(a: { updatedAt: string }, b: { updatedAt: string }): number {
  return b.updatedAt.localeCompare(a.updatedAt)
}

/**
 * Weiter-Aktion eines Laufs (aus Richtung C). Rein frontend-seitig
 * aus dem juengsten Job abgeleitet — keine neuen Endpoints
 * (PLAN.md-Festlegung: useNextStep bleibt im Frontend).
 */
export function nextActionFor(latest: RunDetail, t: Translate): NextAction | null {
  const simId = linkedString(latest, 'simulation_id')
  const projId = linkedString(latest, 'project_id')
  const reportId = linkedString(latest, 'report_id')

  if (latest.status === 'processing' || latest.status === 'pending') {
    if (latest.run_type === 'simulation_run' && simId) {
      return { label: t('shelf.action.watch'), to: { name: 'StepSimulationFeed', params: { simulationId: simId } }, kind: 'neutral' }
    }
    return { label: t('shelf.action.watch'), to: { name: 'RunDetail', params: { id: latest.run_id } }, kind: 'neutral' }
  }
  if (latest.status === 'paused' && simId) {
    return { label: t('shelf.action.resume'), to: { name: 'StepSimulation', params: { simulationId: simId } }, kind: 'accent' }
  }
  if (latest.status === 'failed') {
    return { label: t('shelf.action.inspectFailure'), to: { name: 'RunDetail', params: { id: latest.run_id } }, kind: 'warn' }
  }
  if (latest.status === 'stopped') {
    // Abgebrochen (Glossar): Teilergebnis ansehen, ggf. neu starten.
    return { label: t('shelf.action.inspectStopped'), to: { name: 'RunDetail', params: { id: latest.run_id } }, kind: 'warn' }
  }
  // completed — je Job-Sorte die naechste Station der Kette.
  switch (latest.run_type) {
    case 'graph_build':
    case 'ontology_generate':
      if (projId) return { label: t('shelf.action.preparePersonas'), to: { name: 'StepEnvSetup', params: { projectId: projId } }, kind: 'accent' }
      return null
    case 'simulation_prepare':
      if (simId) return { label: t('shelf.action.reviewPersonas'), to: { name: 'StepEnvSetup', params: { projectId: simId } }, kind: 'warn' }
      return null
    case 'simulation_run':
      if (reportId) return { label: t('shelf.action.readReport'), to: { name: 'StepReport', params: { reportId } }, kind: 'accent' }
      if (simId) return { label: t('shelf.action.createReport'), to: { name: 'StepSimulation', params: { simulationId: simId } }, kind: 'accent' }
      return null
    case 'report_generate':
      if (reportId) return { label: t('shelf.action.readReport'), to: { name: 'StepReport', params: { reportId } }, kind: 'accent' }
      return null
    default:
      return null
  }
}

/** Statuszeile: nennt den Zustand als Text (Systemregel des Entwurfs). */
function statusLineFor(latest: RunDetail, jobCount: number, t: Translate): string {
  const base = latest.message || t(`shelf.status.${latest.status}`)
  return jobCount > 1 ? `${base} · ${t('shelf.status.jobs', { n: jobCount })}` : base
}

/** Reine Aggregation — getrennt vom Composable, damit sie testbar ist. */
export function buildShelfObjects(
  runs: RunDetail[],
  reports: Report[],
  projects: ProjectResponse[],
  templates: PersonaTemplateRecord[],
  t: Translate,
): ShelfObject[] {
  const objects: ShelfObject[] = []

  // 1. Läufe — Jobs transitiv zu Vorhaben gruppieren, juengster traegt die Zeile.
  const groups = groupJobsByEndeavor(runs)
  const claimedProjects = new Set<string>()
  for (const [key, jobs] of groups) {
    const latest = jobs[0]
    for (const j of jobs) {
      const p = linkedString(j, 'project_id')
      if (p) claimedProjects.add(p)
    }
    const active = ACTIVE_STATUSES.has(latest.status)
      ? {
          runId: latest.run_id,
          status: latest.status as 'pending' | 'processing' | 'paused',
          pausable: latest.run_type === 'simulation_run',
          simulationId: linkedString(latest, 'simulation_id'),
          progress: typeof latest.progress === 'number' ? latest.progress : null,
        }
      : null
    objects.push({
      kind: 'lauf',
      id: key,
      title: latest.summary?.document_name || latest.summary?.graph_name || key,
      statusLine: statusLineFor(latest, jobs.length, t),
      updatedAt: latest.updated_at,
      metaId: key,
      nextAction: nextActionFor(latest, t),
      active,
    })
  }

  // 2. Berichte — immer eigene Objekte, auch wenn ein Lauf sie erwaehnt.
  for (const r of reports) {
    const sections = r.outline?.sections?.length ?? 0
    objects.push({
      kind: 'bericht',
      id: r.report_id,
      title: r.simulation_requirement?.slice(0, 80) || r.report_id,
      statusLine:
        r.status === 'completed'
          ? t('shelf.status.reportSections', { n: sections })
          : statusText(t, `shelf.status.report_${r.status}`, r.status),
      updatedAt: r.completed_at || r.created_at || '',
      metaId: r.report_id,
      simulationId: r.simulation_id || null,
      nextAction: {
        label: t('shelf.action.readReport'),
        to: { name: 'StepReport', params: { reportId: r.report_id } },
        kind: 'accent',
      },
      active: null,
    })
  }

  // 3. Graphen — nur Projekte, die KEIN Lauf beansprucht (Q19/D2:
  //    sonst staende dasselbe Vorhaben zweimal in der Liste).
  for (const p of projects) {
    if (claimedProjects.has(p.project_id)) continue
    objects.push({
      kind: 'graph',
      id: p.project_id,
      title: p.project_name || p.project_id,
      statusLine: statusText(t, `shelf.status.project_${p.status}`, p.status ?? ''),
      updatedAt: (p as { updated_at?: string }).updated_at || (p as { created_at?: string }).created_at || '',
      metaId: p.project_id,
      graphId: p.graph_id ?? null,
      nextAction: p.graph_id
        ? { label: t('shelf.action.viewGraph'), to: { name: 'StepGraphBuild', params: { projectId: p.project_id } }, kind: 'neutral' }
        : null,
      active: null,
    })
  }

  // 4. Personasätze
  for (const tpl of templates) {
    const id = tpl.template_id || tpl.username || tpl.name || ''
    if (!id) continue
    objects.push({
      kind: 'personasatz',
      id,
      title: tpl.name || tpl.username || id,
      statusLine: tpl.persona ? String(tpl.persona).slice(0, 96) : t('shelf.status.personaTemplate'),
      updatedAt: (tpl as { updated_at?: string }).updated_at || (tpl as { created_at?: string }).created_at || '',
      metaId: id,
      nextAction: null,
      active: null,
    })
  }

  objects.sort(newestFirst)
  return objects
}

export function useShelf(t: Translate) {
  const objects = ref<ShelfObject[]>([])
  const jobs = ref<ShelfJobRow[]>([])
  const filter = ref<ShelfFilter>('alle')
  const loading = ref(false)
  const error = ref('')

  const filtered = computed(() => {
    if (filter.value === 'alle' || filter.value === 'jobs') return objects.value
    return objects.value.filter((o) => o.kind === filter.value)
  })

  const counts = computed(() => {
    const c: Record<string, number> = { alle: objects.value.length, lauf: 0, bericht: 0, personasatz: 0, graph: 0 }
    for (const o of objects.value) c[o.kind] += 1
    return c
  })

  /** Aktive Objekte — speisen den globalen Topbar-Indikator. */
  const activeObjects = computed(() => objects.value.filter((o) => o.active !== null))

  async function reload(): Promise<void> {
    loading.value = true
    error.value = ''
    // Vier unabhaengige Quellen: eine kaputte Quelle laesst die
    // anderen drei stehen (Promise.allSettled statt all).
    const [runsRes, reportsRes, projectsRes, templatesRes] = await Promise.allSettled([
      listRuns({ limit: 200 }),
      listReports({ limit: 100 }),
      listProjects({ limit: 100 }),
      listPersonaTemplates(),
    ])
    const runs: RunDetail[] =
      runsRes.status === 'fulfilled' ? ((runsRes.value as { data?: { runs?: RunDetail[] } }).data?.runs ?? []) : []
    const reports: Report[] =
      reportsRes.status === 'fulfilled' ? (((reportsRes.value as { data?: unknown }).data as Report[] | undefined) ?? []) : []
    const projects: ProjectResponse[] =
      projectsRes.status === 'fulfilled' ? (((projectsRes.value as { data?: unknown }).data as ProjectResponse[] | undefined) ?? []) : []
    // Die Templates liegen in envelope.data.templates — NICHT direkt auf
    // der Envelope. Der Interceptor gibt die Huelle zurueck, nicht ihr data.
    const templates: PersonaTemplateRecord[] =
      templatesRes.status === 'fulfilled' && templatesRes.value?.success
        ? (templatesRes.value.data?.templates ?? [])
        : []
    const failures = [runsRes, reportsRes, projectsRes, templatesRes].filter((r) => r.status === 'rejected').length
    if (failures > 0) error.value = t('shelf.partialLoad', { n: failures })

    objects.value = buildShelfObjects(runs, Array.isArray(reports) ? reports : [], Array.isArray(projects) ? projects : [], Array.isArray(templates) ? templates : [], t)
    jobs.value = runs
      .map((r) => ({
        runId: r.run_id,
        runType: r.run_type,
        status: r.status,
        message: r.message,
        updatedAt: r.updated_at,
        progress: r.progress,
      }))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    loading.value = false
  }

  return { objects, jobs, filter, filtered, counts, activeObjects, loading, error, reload }
}
