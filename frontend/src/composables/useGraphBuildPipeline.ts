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
  type TaskStatusResponse,
} from '../api/graph'
import { usePolling } from './usePolling'
import { useSystemLog } from './useSystemLog'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { storedEffectiveModel } from './useEnvForm'
import { runtimeLlmPayloadFromStorage } from './useRuntimeLlmOptions'

type RouterAdapter = {
  replace: (location: { name: string; params: Record<string, string> }) => Promise<unknown> | void
}

type Translate = (key: string) => string

export function useGraphBuildPipeline({
  projectId,
  router,
  t,
}: {
  projectId: MaybeRef<string>
  router: RouterAdapter
  t: Translate
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
  let activeGeneration = 0
  const { systemLogs, addLog } = useSystemLog({ cap: 100 })

  const taskPolling = usePolling(async () => {
    if (currentTaskId.value) await pollTaskStatus(currentTaskId.value)
  }, 2000)
  const graphPolling = usePolling(fetchGraphData, 10000)

  function messageFor(errorValue: unknown): string {
    return errorValue instanceof Error ? errorValue.message : String(errorValue)
  }

  function updatePhaseByStatus(status?: string): void {
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

      if (pending.llmProfileId) {
        formData.append('llm_profile_id', pending.llmProfileId)
      } else {
        const selectedModel = storedEffectiveModel()
        if (selectedModel) formData.append('llm_model', selectedModel)
        const runtimeProvider = runtimeLlmPayloadFromStorage()
        if (runtimeProvider) formData.append('llm_provider', JSON.stringify(runtimeProvider))
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
      await router.replace({ name: 'StepGraphBuild', params: { projectId: response.data.project_id } })
      if (isCurrent(generation)) await startBuildGraph(generation)
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
        await startBuildGraph(generation)
      } else if (response.data.status === 'graph_building' && response.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(response.data.graph_build_task_id)
        startGraphPolling()
      } else if ((response.data.status === 'graph_completed' || response.data.status === 'completed') && response.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(response.data.graph_id, generation)
      }
    } catch (caughtError) {
      if (!isCurrent(generation)) return
      error.value = messageFor(caughtError)
      addLog(error.value)
    } finally {
      if (isCurrent(generation)) loading.value = false
    }
  }

  async function startBuildGraph(generation: number): Promise<void> {
    try {
      currentPhase.value = 1
      buildProgress.value = { progress: 0, message: t('step1.build.running') }
      const payload: BuildGraphData = { project_id: currentProjectId.value }
      const selectedModel = storedEffectiveModel()
      if (selectedModel) payload.llm_model = selectedModel
      const runtimeProvider = runtimeLlmPayloadFromStorage()
      if (runtimeProvider) payload.llm_provider = runtimeProvider

      const response = await buildGraph(payload)
      if (!isCurrent(generation)) return
      if (!response.success) {
        error.value = response.error || t('errors.unknown')
        addLog(error.value)
        return
      }

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
    systemLogs,
    initialize,
  }
}
