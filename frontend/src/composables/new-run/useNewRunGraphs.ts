/**
 * Vorhandene Graphen für den Startdialog: Projekte mit `status === 'graph_completed'`
 * (Quelle wie die Graphen-Bibliothek: `GET /api/graph/project/list`). Jeder
 * Eintrag wird einzeln gegen `ProjectSchema` geprüft; unlesbare Einträge werden
 * gezählt statt verschluckt.
 */
import { ref } from 'vue'
import { listProjects } from '@/api/graph'
import { ProjectSchema } from '@/contracts/projectContract'
import { errorText } from '@/composables/graph-library/useProjectGraph'

export interface NewRunGraphOption {
  projectId: string
  graphId: string
  name: string
  updatedAt: string
  /** Frage des Projekts (`simulation_requirement`), falls vorhanden. */
  question: string | null
}

export function useNewRunGraphs() {
  const graphs = ref<NewRunGraphOption[]>([])
  const loading = ref(false)
  const error = ref('')
  const rejected = ref(0)

  async function load(fallbackError: string): Promise<void> {
    loading.value = true
    error.value = ''
    rejected.value = 0
    try {
      const res = await listProjects({ limit: 100 })
      if (!res.success) {
        error.value = res.error || fallbackError
        graphs.value = []
        return
      }
      const items: unknown[] = Array.isArray(res.data) ? res.data : []
      const ok: NewRunGraphOption[] = []
      for (const item of items) {
        const parsed = ProjectSchema.safeParse(item)
        if (!parsed.success) {
          rejected.value += 1
          continue
        }
        const p = parsed.data
        if (p.status !== 'graph_completed' || p.graph_id === null) continue
        ok.push({
          projectId: p.project_id,
          graphId: p.graph_id,
          name: p.name || p.project_id,
          updatedAt: p.updated_at || p.created_at,
          question: p.simulation_requirement?.trim() ? p.simulation_requirement.trim() : null,
        })
      }
      graphs.value = ok.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    } catch (caught) {
      error.value = errorText(caught, fallbackError)
      graphs.value = []
    } finally {
      loading.value = false
    }
  }

  return { graphs, loading, error, rejected, load }
}
