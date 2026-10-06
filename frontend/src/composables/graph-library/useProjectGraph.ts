/**
 * Laedt den Graphen eines Projekts fuer den Graph-Leser (#1797, Etappe 2).
 *
 * Kennung: die Ablage fuehrt Graphen unter der `project_id` (`ShelfObject.id`),
 * `graph_id` steht nur als Zusatz daneben. `GET /api/graph/project/<id>` liefert
 * Zustand und `graph_id`, `GET /api/graph/data/<graph_id>` die Knoten und Kanten.
 *
 * Zustaende, die die Ansicht getrennt zeigen muss:
 *   loading   – erste Antwort steht aus
 *   error     – Anfrage oder Vertrag gescheitert (sichtbar, nicht still)
 *   no-graph  – das Projekt hat keinen Graphen (nicht gebaut oder Build gescheitert)
 *   building  – der Graph wird gerade gebaut; Fortschritt aus dem Task, soweit er ihn liefert
 *   ready     – Graph geladen; `incomplete` bei abgebrochenem Build (Teilgraph)
 */
import { computed, onBeforeUnmount, ref, shallowRef, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getGraphData, getProject, getTaskStatus } from '@/api/graph'
import { ProjectSchema, type Project } from '@/contracts/projectContract'
import { parseTaskStatusResponse } from '@/contracts/taskStatusContract'
import { GraphDataSchema, buildReaderModel, type GraphData, type ReaderModel } from './graphReaderModel'

export type ProjectGraphState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'no-graph'; reason: 'not-built' | 'failed' }
  | { kind: 'building'; progress: number | null; message: string | null }
  | { kind: 'ready'; incomplete: boolean }

const POLL_MS = 3000

export function errorText(caught: unknown, fallback: string): string {
  if (caught instanceof Error && caught.message) return caught.message
  if (typeof caught === 'string' && caught) return caught
  return fallback
}

export function useProjectGraph(projectId: Ref<string | null>) {
  const { t } = useI18n()
  const state = ref<ProjectGraphState>({ kind: 'idle' })
  const project = shallowRef<Project | null>(null)
  const graphData = shallowRef<GraphData | null>(null)
  const model = computed<ReaderModel | null>(() =>
    graphData.value ? buildReaderModel(graphData.value) : null,
  )

  let seq = 0
  let timer: ReturnType<typeof setInterval> | null = null

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  async function loadGraph(graphId: string): Promise<boolean> {
    const res = await getGraphData(graphId)
    if (!res.success) throw new Error(res.error || t('views.graphLibrary.errors.graphData'))
    const parsed = GraphDataSchema.safeParse(res.data)
    if (!parsed.success) throw new Error(t('views.graphLibrary.errors.schema'))
    graphData.value = parsed.data
    return true
  }

  async function run(silent: boolean): Promise<void> {
    const id = projectId.value
    const mySeq = ++seq
    if (!id) {
      stopPolling()
      project.value = null
      graphData.value = null
      state.value = { kind: 'idle' }
      return
    }
    if (!silent) {
      graphData.value = null
      state.value = { kind: 'loading' }
    }
    try {
      const res = await getProject(id)
      if (mySeq !== seq) return
      if (!res.success) throw new Error(res.error || t('views.graphLibrary.errors.project'))
      const parsed = ProjectSchema.safeParse(res.data)
      if (!parsed.success) throw new Error(t('views.graphLibrary.errors.schema'))
      const p = parsed.data
      project.value = p

      if ((p.status === 'graph_completed' || p.status === 'graph_incomplete') && p.graph_id) {
        stopPolling()
        await loadGraph(p.graph_id)
        if (mySeq !== seq) return
        state.value = { kind: 'ready', incomplete: p.status === 'graph_incomplete' }
        return
      }

      if (p.status === 'graph_building') {
        let progress: number | null = null
        let message: string | null = null
        if (p.graph_build_task_id) {
          try {
            const taskRes = await getTaskStatus(p.graph_build_task_id)
            const task = taskRes.success ? parseTaskStatusResponse(taskRes.data) : null
            if (task) {
              progress = task.progress
              message = task.message || null
            }
          } catch {
            // Der Task kann fehlen (Neustart); der Hinweis bleibt ohne Prozentwert.
          }
        }
        if (p.graph_id) {
          try {
            await loadGraph(p.graph_id)
          } catch {
            // Teilgraph noch nicht lesbar: der naechste Takt versucht es erneut.
          }
        }
        if (mySeq !== seq) return
        state.value = { kind: 'building', progress, message }
        if (timer === null) timer = setInterval(() => void run(true), POLL_MS)
        return
      }

      stopPolling()
      graphData.value = null
      state.value = { kind: 'no-graph', reason: p.status === 'failed' ? 'failed' : 'not-built' }
    } catch (caught) {
      if (mySeq !== seq) return
      stopPolling()
      state.value = { kind: 'error', message: errorText(caught, t('views.graphLibrary.errors.unknown')) }
    }
  }

  watch(projectId, () => void run(false), { immediate: true })
  onBeforeUnmount(() => {
    seq += 1
    stopPolling()
  })

  return { state, project, graphData, model, reload: () => run(false) }
}
