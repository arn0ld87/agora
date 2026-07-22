import { describe, it, expect, beforeEach, vi } from 'vitest'

const graphApi = vi.hoisted(() => ({
  generateOntology: vi.fn(),
  getProject: vi.fn(),
  buildGraph: vi.fn(),
  getTaskStatus: vi.fn(),
  getGraphData: vi.fn(),
}))
const pendingUpload = vi.hoisted(() => ({
  getPendingUpload: vi.fn(),
  clearPendingUpload: vi.fn(),
}))
const polling = vi.hoisted(() => ({
  calls: 0,
  taskStart: vi.fn(),
  taskStop: vi.fn(),
  graphStart: vi.fn(),
  graphStop: vi.fn(),
  taskTick: null as null | (() => Promise<void> | void),
}))

vi.mock('../../api/graph', () => graphApi)
vi.mock('../../store/pendingUpload', () => pendingUpload)
vi.mock('../usePolling', () => ({
  usePolling: (task: () => Promise<void> | void) => {
    const isTaskPolling = polling.calls++ === 0
    if (isTaskPolling) polling.taskTick = task
    return {
      start: isTaskPolling ? polling.taskStart : polling.graphStart,
      stop: isTaskPolling ? polling.taskStop : polling.graphStop,
      tick: vi.fn(),
      isRunning: { value: false },
      isTicking: { value: false },
    }
  },
}))
vi.mock('../useSystemLog', () => ({
  useSystemLog: () => ({ systemLogs: { value: [] }, addLog: vi.fn(), clearLog: vi.fn() }),
}))
vi.mock('../useEnvForm', () => ({ storedEffectiveModel: vi.fn(() => 'fallback-model') }))
vi.mock('../useRuntimeLlmOptions', () => ({
  runtimeLlmPayloadFromStorage: vi.fn(() => ({ provider: 'fallback-provider' })),
}))

import { useGraphBuildPipeline } from '../useGraphBuildPipeline'

const t = (key: string) => key

function createRouter() {
  return { replace: vi.fn() }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('useGraphBuildPipeline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    polling.calls = 0
    polling.taskTick = null
    pendingUpload.getPendingUpload.mockReturnValue({
      isPending: true,
      files: [new File(['source'], 'source.txt', { type: 'text/plain' })],
      simulationRequirement: 'Analyse',
      llmProfileId: 'profile_42',
      numAgents: 30,
      numRounds: 10,
    })
    graphApi.generateOntology.mockResolvedValue({
      success: true,
      data: { project_id: 'project_42', status: 'ontology_generated' },
    })
    graphApi.buildGraph.mockResolvedValue({ success: true, data: { task_id: 'task_42' } })
  })

  it('erzeugt einen neuen Projektgraphen genau einmal und ersetzt die URL durch die konkrete ID', async () => {
    const router = createRouter()
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router, t })

    await pipeline.initialize()

    expect(pendingUpload.clearPendingUpload).toHaveBeenCalledOnce()
    expect(graphApi.generateOntology).toHaveBeenCalledOnce()
    const formData = graphApi.generateOntology.mock.calls[0][0] as FormData
    expect(formData.getAll('files')).toHaveLength(1)
    expect(formData.get('simulation_requirement')).toBe('Analyse')
    expect(formData.get('num_agents')).toBe('30')
    expect(formData.get('num_rounds')).toBe('10')
    expect(formData.get('llm_profile_id')).toBe('profile_42')
    expect(formData.get('llm_model')).toBeNull()
    expect(formData.get('llm_provider')).toBeNull()
    expect(router.replace).toHaveBeenCalledWith({
      name: 'StepGraphBuild',
      params: { projectId: 'project_42' },
    })
    expect(graphApi.buildGraph).toHaveBeenCalledTimes(1)
    expect(graphApi.buildGraph).toHaveBeenCalledWith({ project_id: 'project_42', llm_model: 'fallback-model', llm_provider: { provider: 'fallback-provider' } })
    expect(pipeline.currentProjectId.value).toBe('project_42')
  })

  it('meldet einen fehlenden Pending-Upload, ohne eine Ontologie zu erzeugen', async () => {
    pendingUpload.getPendingUpload.mockReturnValue({ isPending: false, files: [] })
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })

    await pipeline.initialize()

    expect(graphApi.generateOntology).not.toHaveBeenCalled()
    expect(pipeline.error.value).toBe('errors.pendingUploadMissing')
  })

  it('verwendet ohne Profil das Fallback-Modell und den Fallback-Provider im Ontology-FormData', async () => {
    pendingUpload.getPendingUpload.mockReturnValue({
      isPending: true,
      files: [new File(['source'], 'source.txt', { type: 'text/plain' })],
      simulationRequirement: 'Analyse',
      llmProfileId: null,
      numAgents: 30,
      numRounds: 10,
    })
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })

    await pipeline.initialize()

    const formData = graphApi.generateOntology.mock.calls[0][0] as FormData
    expect(formData.get('llm_profile_id')).toBeNull()
    expect(formData.get('llm_model')).toBe('fallback-model')
    expect(formData.get('llm_provider')).toBe(JSON.stringify({ provider: 'fallback-provider' }))
  })

  it('behält Pending Upload bei Ontologiefehler und startet weder Build noch Navigation', async () => {
    graphApi.generateOntology.mockResolvedValue({ success: false, error: 'Ontology failed' })
    const router = createRouter()
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router, t })

    await pipeline.initialize()

    expect(pendingUpload.clearPendingUpload).not.toHaveBeenCalled()
    expect(graphApi.buildGraph).not.toHaveBeenCalled()
    expect(router.replace).not.toHaveBeenCalled()
    expect(pipeline.error.value).toBe('Ontology failed')
  })

  it('behält nach erfolgreicher Ontologie die konkrete ID bei Buildfehler und startet kein Polling', async () => {
    graphApi.buildGraph.mockResolvedValue({ success: false, error: 'Build failed' })
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })

    await pipeline.initialize()

    expect(pendingUpload.clearPendingUpload).toHaveBeenCalledOnce()
    expect(pipeline.currentProjectId.value).toBe('project_42')
    expect(pipeline.error.value).toBe('Build failed')
    expect(polling.taskStart).not.toHaveBeenCalled()
    expect(polling.graphStart).not.toHaveBeenCalled()
  })

  it.each([
    ['ontology_generated', { project_id: 'project_42', status: 'ontology_generated' }, 'starts a build'],
    ['graph_building', { project_id: 'project_42', status: 'graph_building', graph_build_task_id: 'task_42' }, 'continues polling'],
    ['graph_completed', { project_id: 'project_42', status: 'graph_completed', graph_id: 'graph_42' }, 'loads the graph'],
  ])('setzt einen konkreten Projektstatus %s fort (%s)', async (_status, project, expected) => {
    graphApi.getProject.mockResolvedValue({ success: true, data: project })
    graphApi.getGraphData.mockResolvedValue({ success: true, data: { graph_id: 'graph_42', nodes: [], edges: [] } })
    const pipeline = useGraphBuildPipeline({ projectId: 'project_42', router: createRouter(), t })

    await pipeline.initialize()

    expect(pipeline.projectData.value).toEqual(project)
    if (expected === 'starts a build') {
      expect(graphApi.buildGraph).toHaveBeenCalledOnce()
      expect(pipeline.currentPhase.value).toBe(1)
    }
    if (expected === 'continues polling') {
      expect(graphApi.buildGraph).not.toHaveBeenCalled()
      expect(polling.taskStart).toHaveBeenCalledOnce()
      expect(polling.graphStart).toHaveBeenCalledOnce()
      expect(pipeline.currentPhase.value).toBe(1)
    }
    if (expected === 'loads the graph') {
      expect(graphApi.getGraphData).toHaveBeenCalledWith('graph_42')
      expect(pipeline.graphData.value).toEqual({ graph_id: 'graph_42', nodes: [], edges: [] })
      expect(pipeline.currentPhase.value).toBe(2)
    }
  })

  it('lädt bei einer echten A→B-Routennavigation das neue konkrete Projekt', async () => {
    graphApi.getProject
      .mockResolvedValueOnce({ success: true, data: { project_id: 'project_a', status: 'graph_completed', graph_id: 'graph_a' } })
      .mockResolvedValueOnce({ success: true, data: { project_id: 'project_b', status: 'graph_completed', graph_id: 'graph_b' } })
    graphApi.getGraphData
      .mockResolvedValueOnce({ success: true, data: { graph_id: 'graph_a', nodes: [], edges: [] } })
      .mockResolvedValueOnce({ success: true, data: { graph_id: 'graph_b', nodes: [], edges: [] } })
    const pipeline = useGraphBuildPipeline({ projectId: 'project_a', router: createRouter(), t })

    await pipeline.initialize()
    await pipeline.initialize('project_b')

    expect(graphApi.getProject).toHaveBeenNthCalledWith(1, 'project_a')
    expect(graphApi.getProject).toHaveBeenNthCalledWith(2, 'project_b')
    expect(pipeline.currentProjectId.value).toBe('project_b')
    expect(pipeline.projectData.value).toMatchObject({ project_id: 'project_b' })
  })

  it('ignoriert eine späte A-Antwort, nachdem die Route bereits auf B gewechselt ist', async () => {
    const slowA = deferred<{ success: boolean; data: { project_id: string; status: string; graph_id: string } }>()
    graphApi.getProject.mockImplementation((projectId: string) => (
      projectId === 'project_a'
        ? slowA.promise
        : Promise.resolve({ success: true, data: { project_id: 'project_b', status: 'graph_completed', graph_id: 'graph_b' } })
    ))
    graphApi.getGraphData.mockResolvedValue({ success: true, data: { graph_id: 'graph_b', nodes: [], edges: [] } })
    const pipeline = useGraphBuildPipeline({ projectId: 'project_a', router: createRouter(), t })

    const loadA = pipeline.initialize()
    await pipeline.initialize('project_b')
    slowA.resolve({ success: true, data: { project_id: 'project_a', status: 'graph_completed', graph_id: 'graph_a' } })
    await loadA

    expect(pipeline.currentProjectId.value).toBe('project_b')
    expect(pipeline.projectData.value).toMatchObject({ project_id: 'project_b' })
    expect(pipeline.graphData.value).toMatchObject({ graph_id: 'graph_b' })
  })

  it('stoppt bei fehlgeschlagenem Graph-Build Task- und Graph-Polling', async () => {
    graphApi.getProject.mockResolvedValue({
      success: true,
      data: { project_id: 'project_42', status: 'graph_building', graph_build_task_id: 'task_42' },
    })
    graphApi.getTaskStatus.mockResolvedValue({ success: true, data: { status: 'failed', error: 'Build failed' } })
    const pipeline = useGraphBuildPipeline({ projectId: 'project_42', router: createRouter(), t })

    await pipeline.initialize()
    await polling.taskTick?.()

    expect(polling.taskStop).toHaveBeenCalledOnce()
    expect(polling.graphStop).toHaveBeenCalledOnce()
    expect(pipeline.error.value).toBe('Build failed')
  })
})
