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
const modelSelection = vi.hoisted(() => ({
  effectiveRef: null as {
    provider_connection_id: string
    model_id: string
    source: string
  } | null,
  runOverride: null as {
    provider_connection_id: string
    model_id: string
    source: string
  } | null,
  ensureLoaded: vi.fn(),
  getRunModelOverride: vi.fn(),
}))
const legacyStorageValues = new Map<string, string>()
const localStorageMock = {
  getItem: (key: string) => legacyStorageValues.get(key) ?? null,
  setItem: (key: string, value: string) => { legacyStorageValues.set(key, value) },
  removeItem: (key: string) => { legacyStorageValues.delete(key) },
  clear: () => { legacyStorageValues.clear() },
}
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
vi.mock('../useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: { get value() { return modelSelection.effectiveRef } },
    effectiveRoute: { value: null },
    loading: { value: false },
    error: { value: null },
    ensureLoaded: modelSelection.ensureLoaded,
    setGlobalSelection: vi.fn(),
  }),
}))
vi.mock('../../store/runModelOverride', () => ({
  getRunModelOverride: modelSelection.getRunModelOverride,
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
    vi.stubGlobal('localStorage', localStorageMock)
    localStorageMock.clear()
    modelSelection.effectiveRef = null
    modelSelection.runOverride = null
    modelSelection.ensureLoaded.mockResolvedValue(undefined)
    modelSelection.getRunModelOverride.mockImplementation(() => modelSelection.runOverride)
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
    expect(graphApi.buildGraph).toHaveBeenCalledWith({ project_id: 'project_42' })
    expect(pipeline.currentProjectId.value).toBe('project_42')
  })

  it('meldet einen fehlenden Pending-Upload, ohne eine Ontologie zu erzeugen', async () => {
    pendingUpload.getPendingUpload.mockReturnValue({ isPending: false, files: [] })
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })

    await pipeline.initialize()

    expect(graphApi.generateOntology).not.toHaveBeenCalled()
    expect(pipeline.error.value).toBe('errors.pendingUploadMissing')
  })

  it('verwendet ohne Profil den Run-Override als vollständige ai_model_ref vor dem Kanon und behält die Connection', async () => {
    pendingUpload.getPendingUpload.mockReturnValue({
      isPending: true,
      files: [new File(['source'], 'source.txt', { type: 'text/plain' })],
      simulationRequirement: 'Analyse',
      llmProfileId: null,
      numAgents: 30,
      numRounds: 10,
    })
    // Gleiche model_id auf zwei Connections: Nur der vollständige Ref kann
    // die explizit gewählte Connection zuverlässig erhalten.
    modelSelection.effectiveRef = {
      provider_connection_id: 'conn-workspace',
      model_id: 'shared-model',
      source: 'workspace-default',
    }
    modelSelection.runOverride = {
      provider_connection_id: 'conn-run',
      model_id: 'shared-model',
      source: 'run-override',
    }
    localStorageMock.setItem('agora.lastModel', 'custom')
    localStorageMock.setItem('agora.lastCustomModel', 'legacy-model')
    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })

    await pipeline.initialize()

    const formData = graphApi.generateOntology.mock.calls[0][0] as FormData
    expect(formData.get('llm_profile_id')).toBeNull()
    expect(JSON.parse(String(formData.get('ai_model_ref')))).toEqual(modelSelection.runOverride)
    expect(formData.get('llm_model')).toBeNull()
    expect(formData.get('llm_provider')).toBeNull()
    expect(graphApi.buildGraph).toHaveBeenCalledWith({
      project_id: 'project_42',
      ai_model_ref: modelSelection.runOverride,
    })
    expect(modelSelection.ensureLoaded).not.toHaveBeenCalled()
    expect(localStorageMock.getItem('agora.lastModel')).toBe('custom')
    expect(localStorageMock.getItem('agora.lastCustomModel')).toBe('legacy-model')
  })

  it('verwendet ohne Run-Override den vollständigen effektiven Kanon-Ref für Ontologie und Build', async () => {
    pendingUpload.getPendingUpload.mockReturnValue({
      isPending: true,
      files: [new File(['source'], 'source.txt', { type: 'text/plain' })],
      simulationRequirement: 'Analyse',
      llmProfileId: null,
      numAgents: 30,
      numRounds: 10,
    })
    modelSelection.effectiveRef = {
      provider_connection_id: 'conn-workspace',
      model_id: 'shared-model',
      source: 'workspace-default',
    }

    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })
    await pipeline.initialize()

    const formData = graphApi.generateOntology.mock.calls[0][0] as FormData
    expect(JSON.parse(String(formData.get('ai_model_ref')))).toEqual(modelSelection.effectiveRef)
    expect(graphApi.buildGraph).toHaveBeenCalledWith({
      project_id: 'project_42',
      ai_model_ref: modelSelection.effectiveRef,
    })
    expect(modelSelection.ensureLoaded).toHaveBeenCalledTimes(1)
  })

  it('sendet ohne Override und ohne Kanon keine Routingfelder und ignoriert liegengebliebene Legacy-Werte', async () => {
    pendingUpload.getPendingUpload.mockReturnValue({
      isPending: true,
      files: [new File(['source'], 'source.txt', { type: 'text/plain' })],
      simulationRequirement: 'Analyse',
      llmProfileId: null,
      numAgents: 30,
      numRounds: 10,
    })
    localStorageMock.setItem('agora.lastModel', 'custom')
    localStorageMock.setItem('agora.lastCustomModel', 'legacy-model')

    const pipeline = useGraphBuildPipeline({ projectId: 'new', router: createRouter(), t })
    await pipeline.initialize()

    const formData = graphApi.generateOntology.mock.calls[0][0] as FormData
    expect(formData.get('ai_model_ref')).toBeNull()
    expect(formData.get('llm_model')).toBeNull()
    expect(formData.get('llm_provider')).toBeNull()
    expect(graphApi.buildGraph).toHaveBeenCalledWith({ project_id: 'project_42' })
    expect(localStorageMock.getItem('agora.lastModel')).toBe('custom')
    expect(localStorageMock.getItem('agora.lastCustomModel')).toBe('legacy-model')
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

  it('restored ontology_generated mit Profil startet den Build ohne ai_model_ref und ohne Resolver', async () => {
    modelSelection.runOverride = {
      provider_connection_id: 'conn-run',
      model_id: 'shared-model',
      source: 'run-override',
    }
    modelSelection.effectiveRef = {
      provider_connection_id: 'conn-workspace',
      model_id: 'shared-model',
      source: 'workspace-default',
    }
    graphApi.getProject.mockResolvedValue({
      success: true,
      data: {
        project_id: 'project_profile',
        status: 'ontology_generated',
        llm_profile_id: 'profile_42',
      },
    })
    const pipeline = useGraphBuildPipeline({ projectId: 'project_profile', router: createRouter(), t })

    await pipeline.initialize()

    expect(graphApi.buildGraph).toHaveBeenCalledWith({ project_id: 'project_profile' })
    expect(modelSelection.getRunModelOverride).not.toHaveBeenCalled()
    expect(modelSelection.ensureLoaded).not.toHaveBeenCalled()
  })

  it.each([
    {
      label: 'Run-Override',
      override: {
        provider_connection_id: 'conn-run',
        model_id: 'shared-model',
        source: 'run-override',
      },
      effective: {
        provider_connection_id: 'conn-workspace',
        model_id: 'shared-model',
        source: 'workspace-default',
      },
      expectedConnection: 'conn-run',
      ensureCalls: 0,
    },
    {
      label: 'Kanon',
      override: null,
      effective: {
        provider_connection_id: 'conn-workspace',
        model_id: 'shared-model',
        source: 'workspace-default',
      },
      expectedConnection: 'conn-workspace',
      ensureCalls: 1,
    },
  ])('restored ontology_generated ohne Profil verwendet $label als vollständigen Ref', async ({
    override,
    effective,
    expectedConnection,
    ensureCalls,
  }) => {
    modelSelection.runOverride = override
    modelSelection.effectiveRef = effective
    graphApi.getProject.mockResolvedValue({
      success: true,
      data: { project_id: 'project_restore', status: 'ontology_generated', llm_profile_id: null },
    })
    const pipeline = useGraphBuildPipeline({ projectId: 'project_restore', router: createRouter(), t })

    await pipeline.initialize()

    expect(graphApi.buildGraph).toHaveBeenCalledWith({
      project_id: 'project_restore',
      ai_model_ref: {
        provider_connection_id: expectedConnection,
        model_id: 'shared-model',
        source: override?.source ?? effective.source,
      },
    })
    expect(modelSelection.ensureLoaded).toHaveBeenCalledTimes(ensureCalls)
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
