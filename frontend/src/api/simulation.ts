import service from './index'
import { z } from 'zod'
import type { LlmRuntimePayload } from './llmRuntime'
import type { PersonaQuotaPlan } from '../contracts/personaQuotaContract'
import type { AiModelRefPayload } from './report'
import {
  PostCreatedEventSchema,
  type PostCreatedEvent,
} from '../contracts/postEventContract'

// --- Local types --------------------------------------------------------

export type SimulationPlatform = 'reddit' | 'twitter'

export interface CreateSimulationData {
  project_id: string
  graph_id?: string
  enable_twitter?: boolean
  enable_reddit?: boolean
}

export interface PrepareSimulationData {
  simulation_id: string
  entity_types?: string[]
  use_llm_for_profiles?: boolean
  parallel_profile_count?: number
  force_regenerate?: boolean
  quota_plan?: PersonaQuotaPlan
  llm_model?: string
  llm_provider?: LlmRuntimePayload
  language?: string
  max_agents?: number
}

export interface TaskStatusData {
  task_id?: string
  simulation_id?: string
  status?: string
  progress?: number
  message?: string
  error?: string | null
}

export interface StartSimulationData {
  simulation_id: string
  platform?: SimulationPlatform
  max_rounds?: number
  simulation_days?: number
  enable_graph_memory_update?: boolean
  /** Legacy-Kompatibilität; bei gesetztem `ai_model_ref` nicht mitsenden. */
  llm_model?: string
  /** Legacy-Kompatibilität; bei gesetztem `ai_model_ref` nicht mitsenden. */
  llm_provider?: LlmRuntimePayload
  /** Autoritative UI-Auswahl (Connection+Modell). Bindet Base-URL und Secret
   * derselben ProviderConnection an die OASIS-Route — kein .env-Fallback.
   * Darf nicht mit `llm_model`/`llm_provider` kombiniert werden. */
  ai_model_ref?: AiModelRefPayload
  /** Issue #764: optionale Token-/Kosten-/Zeit-/Aufruflimits (weich/hart). */
  budget?: import('../contracts/runBudgetContract').RunBudgetConfig
  force?: boolean
}

export interface StopSimulationData {
  simulation_id: string
}

export interface SimulationRecord {
  simulation_id: string
  project_id: string
  status: string
  platform?: SimulationPlatform
  [key: string]: unknown
}

export interface ProfileRecord {
  username: string
  name?: string
  bio?: string
  persona?: string
  platform?: SimulationPlatform
  review_status?: string
  [key: string]: unknown
}

export interface ProfileQualityResponse {
  simulation_id: string
  profiles: Array<{
    username: string
    quality_score: number
    issues: string[]
  }>
  [key: string]: unknown
}

export interface RunStatusResponse {
  simulation_id: string
  status: string
  current_round?: number
  max_rounds?: number
  paused?: boolean
  [key: string]: unknown
}

export interface EnvStatusData {
  simulation_id: string
}

export interface CloseEnvData {
  simulation_id: string
  timeout?: number
}

export interface InterviewAgentsData {
  simulation_id: string
  interviews: Array<{ agent_id: string; prompt: string }>
}

export interface ModelPreset {
  id: string
  name: string
  provider: string
  [key: string]: unknown
}

export interface AvailableModelsResponse {
  models: ModelPreset[]
  [key: string]: unknown
}

export interface BranchData {
  branch_name?: string
  [key: string]: unknown
}

export interface BranchRecord {
  branch_id: string
  branch_name: string
  parent_simulation_id: string
  [key: string]: unknown
}

export interface PersonaTemplateRecord {
  template_id?: string
  username?: string
  name?: string
  bio?: string
  persona?: string
  [key: string]: unknown
}

export interface SimulationActionsParams {
  limit?: number
  offset?: number
  platform?: SimulationPlatform
  agent_id?: string
  round_num?: number
}

export interface TimelineResponse {
  simulation_id: string
  rounds: Array<{
    round_num: number
    post_count: number
    [key: string]: unknown
  }>
}

export interface AgentStatsResponse {
  simulation_id: string
  agents: Array<Record<string, unknown>>
}

// --- API functions -------------------------------------------------------

/**
 * Create simulation
 * @param data - { project_id, graph_id?, enable_twitter?, enable_reddit? }
 */
export const createSimulation = (data: CreateSimulationData): Promise<SimulationRecord> => {
  return service.post('/api/simulation/create', data)
}

/**
 * Prepare simulation environment (async task)
 * @param data - { simulation_id, entity_types?, use_llm_for_profiles?, parallel_profile_count?, force_regenerate? }
 */
export const prepareSimulation = (data: PrepareSimulationData): Promise<TaskStatusData> => {
  return service.post('/api/simulation/prepare', data)
}

/**
 * Query prepare task progress
 * @param data - { task_id?, simulation_id? }
 */
export const getPrepareStatus = (data: TaskStatusData): Promise<TaskStatusData> => {
  return service.post('/api/simulation/prepare/status', data)
}

/**
 * Get simulation status
 * @param simulationId
 */
export const getSimulation = (simulationId: string): Promise<SimulationRecord> => {
  return service.get(`/api/simulation/${simulationId}`)
}

/**
 * Get Agent Profiles for simulation
 * @param simulationId
 * @param platform - 'reddit' | 'twitter'
 */
export const getSimulationProfiles = (
  simulationId: string,
  platform: SimulationPlatform = 'reddit'
): Promise<ProfileRecord[]> => {
  return service.get(`/api/simulation/${simulationId}/profiles`, { params: { platform } })
}

/**
 * Get Agent Profiles being generated in real-time
 * @param simulationId
 * @param platform - 'reddit' | 'twitter'
 */
export const getSimulationProfilesRealtime = (
  simulationId: string,
  platform: SimulationPlatform = 'reddit'
): Promise<ProfileRecord[]> => {
  return service.get(`/api/simulation/${simulationId}/profiles/realtime`, { params: { platform } })
}

/**
 * Get simulation configuration
 * @param simulationId
 */
export const getSimulationConfig = (simulationId: string): Promise<Record<string, unknown>> => {
  return service.get(`/api/simulation/${simulationId}/config`)
}

/**
 * Get simulation configuration being generated in real-time
 * @param simulationId
 * @returns Returns configuration information containing metadata and config content
 */
export const getSimulationConfigRealtime = (
  simulationId: string
): Promise<Record<string, unknown>> => {
  return service.get(`/api/simulation/${simulationId}/config/realtime`)
}

/**
 * List all simulations
 * @param projectId - Optional, filter by project ID
 */
export const listSimulations = (projectId?: string): Promise<SimulationRecord[]> => {
  const params = projectId ? { project_id: projectId } : {}
  return service.get('/api/simulation/list', { params })
}

/**
 * Start simulation
 * @param data - { simulation_id, platform?, max_rounds?, simulation_days?, enable_graph_memory_update? }
 */
export const startSimulation = (data: StartSimulationData): Promise<RunStatusResponse> => {
  return service.post('/api/simulation/start', data)
}

/**
 * Stop simulation
 * @param data - { simulation_id }
 */
export const stopSimulation = (data: StopSimulationData): Promise<RunStatusResponse> => {
  return service.post('/api/simulation/stop', data)
}

/**
 * Get simulation real-time run status
 * @param simulationId
 */
export const getRunStatus = (simulationId: string): Promise<RunStatusResponse> => {
  return service.get(`/api/simulation/${simulationId}/run-status`)
}

/**
 * Get simulation detailed run status (including recent actions)
 * @param simulationId
 */
export const getRunStatusDetail = (simulationId: string): Promise<RunStatusResponse> => {
  return service.get(`/api/simulation/${simulationId}/run-status/detail`)
}

/**
 * Get posts from simulation
 * @param simulationId
 * @param platform - 'reddit' | 'twitter'
 * @param limit - Number of results
 * @param offset - Offset
 */
export const getSimulationPosts = (
  simulationId: string,
  platform: SimulationPlatform = 'reddit',
  limit = 50,
  offset = 0
): Promise<unknown[]> => {
  return service.get(`/api/simulation/${simulationId}/posts`, {
    params: { platform, limit, offset }
  })
}

/**
 * Get feed snapshot — initialer Bestand beim Mount der Feed-View (#1009).
 *
 * Joined die SQLite-Post-/-Comment-/-User-Tabellen gegen die Profil-Datei
 * und liefert eine chronologisch sortierte Liste validierter
 * PostCreatedEvent-Objekte. `persona_name` und `voice_register` werden aus
 * dem Profil aufgelöst (keine erfundenen Werte).
 *
 * @param simulationId
 * @param platform - 'reddit' | 'twitter'
 */
export const getSimulationFeedSnapshot = async (
  simulationId: string,
  platform: SimulationPlatform
): Promise<PostCreatedEvent[]> => {
  // Der Response-Interceptor in api/index.ts entpackt die Axios-Hülle und
  // gibt den Envelope-Body ({ success, data }) zurück; daher casten wir auf
  // den Body-Typ, nicht auf AxiosResponse.
  const envelope = (await service.get(
    `/api/simulation/${simulationId}/feed-snapshot`,
    { params: { platform } }
  )) as unknown as {
    success: boolean
    data: { posts: PostCreatedEvent[] }
  }
  const posts = envelope?.data?.posts ?? []
  // Gegen den Layer-0-Vertrag validieren (persona_name + voice_register
  // Pflicht); invalide Einträge fallen still raus, statt den ganzen Feed
  // beim Mount zu brechen — eine teilweise befüllte Spalte ist besser als
  // eine leere.
  return posts
    .map((p) => PostCreatedEventSchema.safeParse(p))
    .filter((r): r is z.ZodSafeParseSuccess<PostCreatedEvent> => r.success)
    .map((r) => r.data)
}

/**
 * Get simulation timeline (summarized by rounds)
 * @param simulationId
 * @param startRound - Start round
 * @param endRound - End round
 */
export const getSimulationTimeline = (
  simulationId: string,
  startRound = 0,
  endRound: number | null = null
): Promise<TimelineResponse> => {
  const params: Record<string, unknown> = { start_round: startRound }
  if (endRound !== null) {
    params['end_round'] = endRound
  }
  return service.get(`/api/simulation/${simulationId}/timeline`, { params })
}

/**
 * Get Agent statistics
 * @param simulationId
 */
export const getAgentStats = (simulationId: string): Promise<AgentStatsResponse> => {
  return service.get(`/api/simulation/${simulationId}/agent-stats`)
}

/**
 * Get simulation action history
 * @param simulationId
 * @param params - { limit, offset, platform, agent_id, round_num }
 */
export const getSimulationActions = (
  simulationId: string,
  params: SimulationActionsParams = {}
): Promise<unknown[]> => {
  return service.get(`/api/simulation/${simulationId}/actions`, { params })
}

/**
 * Close simulation environment (graceful shutdown)
 * @param data - { simulation_id, timeout? }
 */
export const closeSimulationEnv = (data: CloseEnvData): Promise<unknown> => {
  return service.post('/api/simulation/close-env', data)
}

/**
 * Get simulation environment status
 * @param data - { simulation_id }
 */
export const getEnvStatus = (data: EnvStatusData): Promise<unknown> => {
  return service.post('/api/simulation/env-status', data)
}

/**
 * Batch interview Agents
 * @param data - { simulation_id, interviews: [{ agent_id, prompt }] }
 */
export const interviewAgents = (data: InterviewAgentsData): Promise<unknown> => {
  return service.post('/api/simulation/interview/batch', data)
}

/**
 * Get simulation history list (with project details)
 * Used to display historical projects on home page
 * @param limit - Return count limit
 */
export const getSimulationHistory = (limit = 20): Promise<SimulationRecord[]> => {
  return service.get('/api/simulation/history', { params: { limit } })
}

/**
 * List installed Ollama + curated LLM model presets for the model dropdown.
 */
export const getAvailableModels = (): Promise<AvailableModelsResponse> => {
  return service.get('/api/simulation/available-models')
}

/**
 * Pause a running simulation between rounds.
 */
export const pauseSimulation = (simulationId: string): Promise<RunStatusResponse> => {
  return service.post(`/api/simulation/${simulationId}/pause`)
}

/**
 * Resume a paused simulation.
 */
export const resumeSimulation = (simulationId: string): Promise<RunStatusResponse> => {
  return service.post(`/api/simulation/${simulationId}/resume`)
}

/**
 * Stream raw stdout/stderr of the OASIS subprocess (terminal view).
 * @param simulationId
 * @param fromLine - incremental polling cursor
 */
export const getSimulationConsoleLog = (
  simulationId: string,
  fromLine = 0
): Promise<{ lines: string[]; from_line: number; total_lines: number }> => {
  return service.get(`/api/simulation/${simulationId}/console-log`, {
    params: { from_line: fromLine }
  })
}

/**
 * Add a manually authored persona to the prepared simulation.
 * @param simulationId
 * @param data - { platform?, username, name, bio, persona, ... }
 */
export const addSimulationProfile = (
  simulationId: string,
  data: Omit<ProfileRecord, 'review_status'>
): Promise<ProfileRecord> => {
  return service.post(`/api/simulation/${simulationId}/profiles`, data)
}

/**
 * Delete a persona by username.
 * @param simulationId
 * @param username
 * @param platform
 */
export const deleteSimulationProfile = (
  simulationId: string,
  username: string,
  platform: SimulationPlatform = 'reddit'
): Promise<unknown> => {
  return service.delete(
    `/api/simulation/${simulationId}/profiles/${encodeURIComponent(username)}`,
    { params: { platform } }
  )
}

/**
 * Edit a persona in-place. Resets review_status to pending unless the caller
 * explicitly sends review_status (Slice 2.1 backend semantics).
 * @param simulationId
 * @param username
 * @param data — editable subset (bio, persona, profession, …)
 */
export const editSimulationProfile = (
  simulationId: string,
  username: string,
  data: Partial<ProfileRecord>
): Promise<ProfileRecord> => {
  return service.patch(
    `/api/simulation/${simulationId}/profiles/${encodeURIComponent(username)}`,
    data
  )
}

/**
 * Approve a persona for the upcoming simulation run.
 * @param simulationId
 * @param username
 * @param notes
 */
export const approveSimulationProfile = (
  simulationId: string,
  username: string,
  notes?: string
): Promise<ProfileRecord> => {
  return service.post(
    `/api/simulation/${simulationId}/profiles/${encodeURIComponent(username)}/approve`,
    notes ? { notes } : {}
  )
}

/**
 * Reject a persona; will be skipped once the start-gate (Slice 2.3) is live.
 * @param simulationId
 * @param username
 * @param reason
 */
export const rejectSimulationProfile = (
  simulationId: string,
  username: string,
  reason?: string
): Promise<ProfileRecord> => {
  return service.post(
    `/api/simulation/${simulationId}/profiles/${encodeURIComponent(username)}/reject`,
    reason ? { reason } : {}
  )
}

/**
 * Trigger a regeneration of a single persona.
 * State-machine: pending|approved|rejected → regenerating → pending.
 * The start-gate blocks while any persona is in regenerating state.
 * @param simulationId
 * @param username
 * @param hint - optional prompt hint for the regeneration
 */
export const regenerateSimulationProfile = (
  simulationId: string,
  username: string,
  hint?: string
): Promise<ProfileRecord> => {
  return service.post(
    `/api/simulation/${simulationId}/profiles/${encodeURIComponent(username)}/regenerate`,
    hint ? { hint } : {}
  )
}

/**
 * Quality heuristics report for the personas of a simulation.
 * @param simulationId
 */
export const getSimulationProfilesQuality = (
  simulationId: string
): Promise<ProfileQualityResponse> => {
  return service.get(`/api/simulation/${simulationId}/profiles/quality`)
}

/**
 * List reusable persona templates stored on the local backend.
 */
export const listPersonaTemplates = (): Promise<PersonaTemplateRecord[]> => {
  return service.get('/api/simulation/persona-library')
}

/**
 * Save a generated or manually authored persona as a reusable template.
 * @param data
 */
export const savePersonaTemplate = (
  data: PersonaTemplateRecord
): Promise<PersonaTemplateRecord> => {
  return service.post('/api/simulation/persona-library', data)
}

/**
 * Delete a reusable persona template.
 * @param templateId
 */
export const deletePersonaTemplate = (templateId: string): Promise<unknown> => {
  return service.delete(`/api/simulation/persona-library/${encodeURIComponent(templateId)}`)
}

export const createSimulationBranch = (
  simulationId: string,
  data: BranchData
): Promise<BranchRecord> => {
  return service.post(`/api/simulation/${simulationId}/branch`, data)
}

export const listSimulationBranches = (simulationId: string): Promise<BranchRecord[]> => {
  return service.get(`/api/simulation/${simulationId}/branches`)
}
