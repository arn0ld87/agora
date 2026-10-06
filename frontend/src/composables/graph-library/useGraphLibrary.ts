/**
 * Datenschicht der Graphen-Bibliothek (#1797, Etappe 2).
 *
 * Die Ablage (`useShelf`) zeigt nur Projekte, die KEIN Lauf beansprucht; die
 * Bibliothek braucht alle. Deshalb liest sie `GET /api/graph/project/list` selbst
 * und zaehlt die Laeufe je `project_id` aus `GET /api/simulation/list`.
 * Eine ausgefallene Quelle wird benannt, nie als „0 Laeufe“ ausgegeben.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { listProjects } from '@/api/graph'
import { listSimulations } from '@/api/simulation'
import { ProjectSchema, type Project } from '@/contracts/projectContract'
import { SimulationRefSchema, type SimulationRef } from './graphReaderModel'
import { errorText } from './useProjectGraph'

export interface LibraryGraph {
  projectId: string
  name: string
  /** Erster Dateiname der Quelle, falls das Projekt Dateien traegt. */
  source: string | null
  extraSources: number
  status: Project['status']
  hasGraph: boolean
  updatedAt: string
  /** `null`: Laeufe konnten nicht geladen werden. */
  runCount: number | null
}

function sourceOf(project: Project): { source: string | null; extra: number } {
  const names: string[] = []
  for (const file of project.files) {
    const name = file['filename'] ?? file['original_filename']
    if (typeof name === 'string' && name) names.push(name)
  }
  return { source: names[0] ?? null, extra: Math.max(0, names.length - 1) }
}

/** Parst jedes Element einzeln; unlesbare Eintraege werden gezaehlt statt verschluckt. */
function parseEach<T>(items: unknown, parse: (item: unknown) => T | null): { ok: T[]; rejected: number } {
  if (!Array.isArray(items)) return { ok: [], rejected: 0 }
  const ok: T[] = []
  let rejected = 0
  for (const item of items) {
    const value = parse(item)
    if (value === null) rejected += 1
    else ok.push(value)
  }
  return { ok, rejected }
}

export function useGraphLibrary() {
  const { t } = useI18n()
  const graphs = ref<LibraryGraph[]>([])
  const loading = ref(false)
  /** Harter Fehler: die Projektliste fehlt. */
  const error = ref('')
  /** Teilausfall: Liste da, aber Laeufe oder einzelne Eintraege fehlen. */
  const notices = ref<string[]>([])

  async function reload(): Promise<void> {
    loading.value = true
    error.value = ''
    notices.value = []
    const [projectsRes, simsRes] = await Promise.allSettled([listProjects({ limit: 100 }), listSimulations()])

    let projects: Project[] = []
    if (projectsRes.status === 'rejected') {
      error.value = errorText(projectsRes.reason, t('views.graphLibrary.errors.unknown'))
    } else if (!projectsRes.value.success) {
      error.value = projectsRes.value.error || t('views.graphLibrary.errors.project')
    } else {
      const parsed = parseEach(projectsRes.value.data, (item) => {
        const r = ProjectSchema.safeParse(item)
        return r.success ? r.data : null
      })
      projects = parsed.ok
      if (parsed.rejected > 0) notices.value.push(t('views.graphLibrary.library.rejected', { n: parsed.rejected }))
    }

    let runCounts: Map<string, number> | null = null
    if (simsRes.status === 'fulfilled' && simsRes.value.success) {
      const parsed = parseEach<SimulationRef>(simsRes.value.data, (item) => {
        const r = SimulationRefSchema.safeParse(item)
        return r.success ? r.data : null
      })
      runCounts = new Map()
      for (const sim of parsed.ok) runCounts.set(sim.project_id, (runCounts.get(sim.project_id) ?? 0) + 1)
    } else {
      notices.value.push(t('views.graphLibrary.library.runsUnavailable'))
    }

    graphs.value = error.value
      ? []
      : projects
          .map((p) => {
            const { source, extra } = sourceOf(p)
            return {
              projectId: p.project_id,
              name: p.name || p.project_id,
              source,
              extraSources: extra,
              status: p.status,
              hasGraph: p.graph_id !== null,
              updatedAt: p.updated_at || p.created_at,
              runCount: runCounts ? (runCounts.get(p.project_id) ?? 0) : null,
            }
          })
          .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    loading.value = false
  }

  const isEmpty = computed(() => !loading.value && !error.value && graphs.value.length === 0)

  return { graphs, loading, error, notices, isEmpty, reload }
}

/** Laeufe, die auf diesem Graphen laufen (`GET /api/simulation/list?project_id=`). */
export function useGraphRuns() {
  const { t } = useI18n()
  const runs = ref<SimulationRef[]>([])
  const loading = ref(false)
  const error = ref('')

  async function load(projectId: string): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const res = await listSimulations(projectId)
      if (!res.success) throw new Error(res.error || t('views.graphLibrary.errors.runs'))
      const parsed = parseEach<SimulationRef>(res.data, (item) => {
        const r = SimulationRefSchema.safeParse(item)
        return r.success ? r.data : null
      })
      if (parsed.rejected > 0) error.value = t('views.graphLibrary.errors.runsPartial', { n: parsed.rejected })
      runs.value = [...parsed.ok].sort((a, b) =>
        (b.created_at ?? b.updated_at ?? '').localeCompare(a.created_at ?? a.updated_at ?? ''),
      )
    } catch (caught) {
      runs.value = []
      error.value = errorText(caught, t('views.graphLibrary.errors.runs'))
    } finally {
      loading.value = false
    }
  }

  return { runs, loading, error, load }
}
