import { ref, unref, type MaybeRef } from 'vue'
import {
  buildGraph,
  generateOntology,
  getGraphData,
  getProject,
  getTaskStatus,
  type BuildGraphData,
  type GraphDataResponse,
  type ProjectResponse,
} from '../api/graph'
import type { AiModelRefPayload } from '../api/report'
import {
  EMPTY_DEGRADATION_REPORT,
  parseDegradationReport,
  type PipelineDegradationReport,
} from '../contracts/pipelineDegradationContract'
import { usePolling } from './usePolling'
import { useSystemLog } from './useSystemLog'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { useRunModelResolver } from './useRunModelResolver'

/** Strukturaequivalent zu vue-routers ``LocationQueryRaw`` — ohne Import, der Adapter bleibt Router-agnostisch. */
type RouteQueryValue = string | number | null | undefined
type RouteQuery = Record<string, RouteQueryValue | RouteQueryValue[]>

type RouterAdapter = {
  replace: (location: {
    name: string
    params: Record<string, string>
    query?: RouteQuery
  }) => Promise<unknown> | void
}

type Translate = (key: string) => string

export function useGraphBuildPipeline({
  projectId,
  router,
  t,
  preserveQuery,
}: {
  projectId: MaybeRef<string>
  router: RouterAdapter
  t: Translate
  /**
   * Query der aktuellen Route. Der interne ``replace`` auf die echte
   * Projekt-ID muss sie mitnehmen, sonst enden die Run-Parameter des
   * Dashboard-Starts in Schritt 1 (Issue #1234).
   */
  preserveQuery?: MaybeRef<RouteQuery>
}) {
  const currentProjectId = ref(String(unref(projectId)))
  const loading = ref(false)
  const graphLoading = ref(false)
  const error = ref('')
  const projectData = ref<ProjectResponse | null>(null)
  const graphData = ref<GraphDataResponse | null>(null)
  const currentPhase = ref(-1)
  const ontologyProgress = ref<unknown>(null)
  const buildProgress = ref<unknown>(null)
  const currentTaskId = ref<string | null>(null)
  // Issue #1023 (Befund B-23): Registry-Run-ID des aktuellen Graph-Builds.
  // Nur im laufenden Session-State verfuegbar — ein Reload nach
  // Build-Abschluss kann sie nicht rekonstruieren (ProjectResponse
  // persistiert keine run_id). StepModelOverrideChip faellt dann auf den
  // Stage-Default zurueck, was der dokumentierte Fallback-Pfad ist.
  const currentRunId = ref<string | null>(null)
  // Issue #1029: stille Teilausfälle des abgeschlossenen Builds. Leer ist
  // der Normalfall. Ein Eintrag hier bedeutet, dass der Build zwar
  // durchgelaufen ist, das Ergebnis aber nachweislich schlechter ist als
  // es aussieht.
  const degradations = ref<PipelineDegradationReport>(EMPTY_DEGRADATION_REPORT)
  let activeGeneration = 0
  const { systemLogs, addLog } = useSystemLog({ cap: 100 })
  const { resolveRunModel } = useRunModelResolver()

  // Der Graph-Build ist ein langlaufender Server-Job (Minuten). Beide Polls
  // müssen auch im Hintergrund-Tab laufen: usePolling startet bei
  // document.hidden=true weder Interval noch Immediate-Tick, d. h. ein Build,
  // der gestartet wird während der Tab nicht sichtbar ist, würde nie
  // eingesammelt werden — der Fortschritts-Spinner bliebe dauerhaft stehen.
  // Analog zu useSimulationPrepare (keep polling even in background tab).
  const taskPolling = usePolling(async () => {
    if (currentTaskId.value) await pollTaskStatus(currentTaskId.value)
  }, 2000, { pauseWhenHidden: false })
  const graphPolling = usePolling(fetchGraphData, 10000, { pauseWhenHidden: false })

  // PR #1371: true, wenn das Projekt einen per Nutzerabbruch behaltenen
  // Teilgraphen traegt (status='graph_incomplete'). Getrennt von den
  // Degradationen, weil ein sauberer Abbruch keine Degradation erzeugt —
  // der Graph ist trotzdem unvollstaendig.
  const graphIncomplete = ref(false)

  function messageFor(errorValue: unknown): string {
    return errorValue instanceof Error ? errorValue.message : String(errorValue)
  }

  function updatePhaseByStatus(status?: string): void {
    graphIncomplete.value = status === 'graph_incomplete'
    switch (status) {
      case 'created':
      case 'ontology_generated':
        currentPhase.value = 0
        break
      case 'graph_building':
        currentPhase.value = 1
        break
      case 'graph_completed':
      case 'completed':
        currentPhase.value = 2
        break
      // PR #1371: Ein abgebrochener Build hinterlässt einen bewusst
      // behaltenen Teilgraphen (status='graph_incomplete', graph_id gesetzt).
      // Ohne diesen Fall bliebe currentPhase=-1 — kein Fehler, kein Graph,
      // kein Weg nach vorn. Phase 2 macht den Graphen ansehbar; den
      // Weiter-Knopf blockiert graphIncomplete ueber qualityBlocked in
      // StepGraphBuildView.
      case 'graph_incomplete':
        currentPhase.value = 2
        break
      case 'failed':
        error.value = t('errors.projectFailed')
        break
    }
  }

  async function initialize(nextProjectId?: string): Promise<void> {
    const generation = ++activeGeneration
    if (nextProjectId && nextProjectId !== currentProjectId.value) {
      stopPolling()
      stopGraphPolling()
      currentProjectId.value = nextProjectId
      error.value = ''
      projectData.value = null
      graphData.value = null
      ontologyProgress.value = null
      buildProgress.value = null
      currentPhase.value = -1
      currentRunId.value = null
      degradations.value = EMPTY_DEGRADATION_REPORT
      graphIncomplete.value = false
    }
    addLog(t('common.starting'))
    if (currentProjectId.value === 'new') {
      await createProjectFromPendingUpload(generation)
      return
    }
    await loadProject(generation)
  }

  function isCurrent(generation: number): boolean {
    return generation === activeGeneration
  }

  async function createProjectFromPendingUpload(generation: number): Promise<void> {
    const pending = getPendingUpload()
    if (!pending.isPending || pending.files.length === 0) {
      if (!isCurrent(generation)) return
      error.value = t('errors.pendingUploadMissing')
      addLog(error.value)
      return
    }

    try {
      loading.value = true
      currentPhase.value = 0
      ontologyProgress.value = { message: t('common.processing') }
      const formData = new FormData()
      pending.files.forEach((file) => formData.append('files', file))
      formData.append('simulation_requirement', pending.simulationRequirement)
      formData.append('num_agents', String(pending.numAgents))
      formData.append('num_rounds', String(pending.numRounds))

      let aiModelRef: AiModelRefPayload | null = null
      if (pending.llmProfileId) {
        formData.append('llm_profile_id', pending.llmProfileId)
      } else {
        aiModelRef = (await resolveRunModel()).ref
        if (aiModelRef) formData.append('ai_model_ref', JSON.stringify(aiModelRef))
      }

      const response = await generateOntology(formData)
      if (!isCurrent(generation)) return
      if (!response.success) {
        error.value = response.error || t('errors.unknown')
        addLog(error.value)
        return
      }

      clearPendingUpload()
      currentProjectId.value = response.data.project_id
      projectData.value = response.data
      ontologyProgress.value = null
      // Die Query trägt die Run-Parameter des Dashboard-Starts weiter. Ohne
      // sie endet die Kette hier: `clearPendingUpload()` eine Zeile darüber
      // hat den Store bereits geräumt (Issue #1234).
      await router.replace({
        name: 'StepGraphBuild',
        params: { projectId: response.data.project_id },
        query: { ...unref(preserveQuery) },
      })
      if (isCurrent(generation)) await startBuildGraph(generation, aiModelRef)
    } catch (caughtError) {
      if (!isCurrent(generation)) return
      error.value = messageFor(caughtError)
      addLog(error.value)
    } finally {
      if (isCurrent(generation)) loading.value = false
    }
  }

  async function loadProject(generation: number): Promise<void> {
    try {
      loading.value = true
      const response = await getProject(currentProjectId.value)
      if (!isCurrent(generation)) return
      if (!response.success) {
        error.value = response.error || t('errors.unknown')
        addLog(error.value)
        return
      }

      projectData.value = response.data
      updatePhaseByStatus(response.data.status)
      if (response.data.status === 'ontology_generated' && !response.data.graph_id) {
        await startBuildGraph(generation, response.data.llm_profile_id ? null : undefined)
      } else if (response.data.status === 'graph_building' && response.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(response.data.graph_build_task_id)
        startGraphPolling()
      } else if ((response.data.status === 'graph_completed' || response.data.status === 'completed') && response.data.graph_id) {
        // Issue #1029: Erst die Befunde des abgeschlossenen Builds holen,
        // dann weiterschalten. Ohne diesen Schritt verlöre ein Reload den
        // blockierenden Befund, und der Weiter-Button wäre wieder offen —
        // ausgerechnet auf dem Weg, den ein Nutzer nach einem
        // fehlgeschlagenen Lauf am ehesten nimmt.
        await restoreDegradations(response.data.graph_build_task_id, generation)
        currentPhase.value = 2
        await loadGraph(response.data.graph_id, generation)
      } else if (response.data.status === 'graph_incomplete' && response.data.graph_id) {
        // PR #1371: Abgebrochener Build, Teilgraph bewusst behalten (Q34).
        // Ansehen ja, weiterarbeiten nein — graphIncomplete blockiert den
        // Weiter-Knopf in StepGraphBuildView, unabhaengig von den
        // Degradationen (die bei sauberem Abbruch leer sein koennen).
        await restoreDegradations(response.data.graph_build_task_id, generation)
        currentPhase.value = 2
        await loadGraph(response.data.graph_id, generation)
        addLog(t('step1.graphIncomplete'))
      }
    } catch (caughtError) {
      if (!isCurrent(generation)) return
      error.value = messageFor(caughtError)
      addLog(error.value)
    } finally {
      if (isCurrent(generation)) loading.value = false
    }
  }

  async function startBuildGraph(
    generation: number,
    resolvedAiModelRef?: AiModelRefPayload | null,
  ): Promise<void> {
    try {
      currentPhase.value = 1
      // Befunde des Vorlaufs gehören nicht zum neuen Build.
      degradations.value = EMPTY_DEGRADATION_REPORT
      buildProgress.value = { progress: 0, message: t('step1.build.running') }
      const payload: BuildGraphData = { project_id: currentProjectId.value }
      const aiModelRef = resolvedAiModelRef === undefined
        ? (await resolveRunModel()).ref
        : resolvedAiModelRef
      if (aiModelRef) payload.ai_model_ref = aiModelRef

      const response = await buildGraph(payload)
      if (!isCurrent(generation)) return
      if (!response.success) {
        error.value = response.error || t('errors.unknown')
        addLog(error.value)
        return
      }

      currentRunId.value = response.data.run_id ?? null
      startGraphPolling()
      startPollingTask(response.data.task_id)
    } catch (caughtError) {
      if (!isCurrent(generation)) return
      error.value = messageFor(caughtError)
      addLog(error.value)
    }
  }

  function startGraphPolling(): void {
    void graphPolling.start({ immediate: true })
  }

  function startPollingTask(taskId: string): void {
    currentTaskId.value = taskId
    void taskPolling.start({ immediate: true })
  }

  async function fetchGraphData(): Promise<void> {
    const generation = activeGeneration
    try {
      const projectResponse = await getProject(currentProjectId.value)
      if (isCurrent(generation) && projectResponse.success && projectResponse.data.graph_id) {
        await loadGraph(projectResponse.data.graph_id, generation)
      }
    } catch (caughtError) {
      if (isCurrent(generation)) addLog(messageFor(caughtError))
    }
  }

  /** Übernimmt die Befunde eines Task-Ergebnisses und protokolliert sie. */
  function applyDegradations(result: Record<string, unknown> | null | undefined): void {
    degradations.value = parseDegradationReport(result)
    for (const event of degradations.value.events) {
      addLog(event.detail)
    }
  }

  /**
   * Holt die Befunde eines bereits abgeschlossenen Builds nach.
   *
   * Der Task ist die einzige Quelle: `ProjectResponse` trägt den Bericht
   * nicht. Ist die Task-ID nach einem Backend-Neustart nicht mehr
   * auflösbar, bleibt der Bericht leer — derselbe dokumentierte
   * Fallback-Pfad wie bei `currentRunId` (#1023).
   */
  async function restoreDegradations(taskId: string | undefined, generation: number): Promise<void> {
    if (!taskId) return
    try {
      const response = await getTaskStatus(taskId)
      if (!isCurrent(generation) || !response.success) return
      if (response.data.status !== 'completed') return
      applyDegradations(response.data.result)
    } catch (caughtError) {
      // Ein nicht mehr auflösbarer Task darf den Wiedereinstieg nicht
      // blockieren — das Nachladen ist eine Verbesserung, kein Vertrag.
      if (isCurrent(generation)) addLog(messageFor(caughtError))
    }
  }

  async function pollTaskStatus(taskId: string): Promise<void> {
    const generation = activeGeneration
    try {
      const response = await getTaskStatus(taskId)
      if (!isCurrent(generation) || !response.success) return

      const task = response.data
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      if (task.status === 'completed') {
        stopPolling()
        stopGraphPolling()
        // Issue #1029: vor dem Weiterschalten auswerten, was still
        // ausgefallen ist. Ein Build kann technisch fertig sein und
        // trotzdem ein Ergebnis liefern, mit dem weiterzuarbeiten sich
        // nicht lohnt.
        applyDegradations(task.result)
        currentPhase.value = 2
        const projectResponse = await getProject(currentProjectId.value)
        if (isCurrent(generation) && projectResponse.success && projectResponse.data.graph_id) {
          projectData.value = projectResponse.data
          await loadGraph(projectResponse.data.graph_id, generation)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        stopGraphPolling()
        error.value = task.error || t('errors.unknown')
        addLog(error.value)
      }
    } catch (caughtError) {
      if (!isCurrent(generation)) return
      error.value = messageFor(caughtError)
      addLog(error.value)
    }
  }

  async function loadGraph(graphId: string, generation: number): Promise<void> {
    graphLoading.value = true
    try {
      const response = await getGraphData(graphId)
      if (isCurrent(generation) && response.success) graphData.value = response.data
    } catch (caughtError) {
      if (!isCurrent(generation)) return
      error.value = messageFor(caughtError)
      addLog(error.value)
    } finally {
      if (isCurrent(generation)) graphLoading.value = false
    }
  }

  function stopPolling(): void {
    taskPolling.stop()
    currentTaskId.value = null
  }

  function stopGraphPolling(): void {
    graphPolling.stop()
  }

  return {
    currentProjectId,
    loading,
    graphLoading,
    error,
    projectData,
    graphData,
    currentPhase,
    ontologyProgress,
    buildProgress,
    currentRunId,
    systemLogs,
    // Issue #1029: stille Teilausfälle des Builds. Leer heißt „nichts
    // ausgefallen", nicht „nicht geprüft".
    degradations,
    graphIncomplete,
    initialize,
    // Issue #1023 (Befund B-08): GraphPanel/GraphToolbar emittieren
    // "refresh" seit jeher, StepGraphBuildView hatte dafuer nie einen
    // Listener. fetchGraphData() re-polled Projekt+Graph bereits intern
    // (Fallback nach Task-Completion) — hier als oeffentliche Funktion
    // fuer den manuellen Refresh-Button verdrahtet.
    refreshGraph: fetchGraphData,
  }
}
