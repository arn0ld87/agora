import service from './index'
import { z } from 'zod'
import type { LlmRuntimePayload } from './llmRuntime'
import type { PersonaQuotaPlan } from '../contracts/personaQuotaContract'
import type { AiModelRefPayload } from './report'
import type { ApiEnvelope } from './envelope'
import {
  PostCreatedEventSchema,
  type PostCreatedEvent,
} from '../contracts/postEventContract'
import type {
  AvailableModelsResponse as AvailableModelsResponseContract,
  ModelPreset as ModelPresetContract,
} from '../contracts/modelPresetContract'

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

/**
 * Gemeinsame Antwortform von `/prepare` und `/prepare/status`.
 *
 * Die unteren Felder liefert das Backend seit laengerem mit, sie fehlten
 * hier aber: `already_prepared` (simulation_prepare.py:554),
 * `expected_entities_count` (ebd. 1068), `persona_target`
 * (contracts/persona_target_contract.py, Issue #1034) und
 * `progress_detail.current_stage` (simulation_prepare.py:822). Ohne sie
 * musste der Aufrufer den Typ lokal erweitern — eine Ergaenzung, die in
 * einem Composable niemand findet.
 */
export interface TaskStatusData {
  task_id?: string
  simulation_id?: string
  status?: string
  progress?: number
  message?: string
  error?: string | null
  already_prepared?: boolean
  expected_entities_count?: number
  persona_target?: unknown
  progress_detail?: {
    current_stage?: string
    [key: string]: unknown
  }
  [key: string]: unknown
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

/**
 * Felder aus `backend/app/services/persona_quality_service.py::evaluate`
 * (ueber `api/simulation_profiles.py::get_simulation_profiles_quality`).
 *
 * Frueher stand hier ein `profiles`-Array — ein Feld, das der Endpunkt
 * nie geliefert hat; es heisst `personas`. Nur die Index-Signatur hat
 * das durchgehen lassen, weshalb der Aufrufer seit jeher Felder las,
 * die im Typ nicht standen.
 */
/**
 * `GET /<id>/profiles/realtime` — die Profile liegen im Feld `profiles`,
 * NICHT direkt in `data` (backend/app/api/simulation_profiles.py:206).
 */
export interface ProfilesRealtimeResponse {
  simulation_id: string
  platform: string
  count: number
  total_expected?: number
  is_generating?: boolean
  file_exists?: boolean
  file_modified_at?: string | null
  profiles: ProfileRecord[]
  [key: string]: unknown
}

/**
 * `GET /<id>/config/realtime` — die Konfiguration liegt im Feld `config`
 * (backend/app/api/simulation_profiles.py:598).
 */
export interface ConfigRealtimeResponse {
  simulation_id: string
  file_exists?: boolean
  file_modified_at?: string | null
  is_generating?: boolean
  generation_stage?: string | null
  config_generated?: boolean
  config: Record<string, unknown> | null
  summary?: Record<string, unknown>
  [key: string]: unknown
}

export interface ProfileQualitySummary {
  total: number
  approved: number
  pending: number
  rejected: number
  role_diversity: number
  mbti_diversity: number
  distinct_roles: string[]
  [key: string]: unknown
}

export interface ProfileQualityIssue {
  code: string
  severity: string
  detail?: Record<string, unknown>
  [key: string]: unknown
}

export interface ProfileQualityResponse {
  simulation_id: string
  summary?: ProfileQualitySummary
  global_issues?: ProfileQualityIssue[]
  personas?: Array<Record<string, unknown>>
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

/**
 * Ein Eintrag aus `presets[]` bzw. `ollama[]` von
 * `backend/app/api/simulation_lifecycle.py::get_available_models`.
 *
 * Issue #1395: Re-Export des generierten Zod-Spiegels
 * (`contracts/modelPresetContract.ts`) statt eines handgeschriebenen
 * Interfaces — der Backend-Vertrag lebt in
 * `backend/app/contracts/model_preset_contract.py`.
 *
 * Issue #1290: `label` traegt fuer kuratierte Presets keinen Text mehr — der
 * Endpunkt liefert stattdessen `label_key`, einen stabilen i18n-Schluessel
 * (`llm.preset.<kind>.<slug>`), den `i18n/modelPresetLabel.ts` aufloest.
 * Die Ollama-Tags-Liste setzt `label` weiterhin auf den Modellnamen.
 */
export type ModelPreset = ModelPresetContract

/**
 * Felder aus `backend/app/api/simulation_lifecycle.py::get_available_models`.
 * Re-Export des generierten Zod-Spiegels (Issue #1395).
 */
export type AvailableModelsResponse = AvailableModelsResponseContract

export interface BranchData {
  branch_name?: string
  [key: string]: unknown
}

/**
 * Ein Branch IST eine Simulation — der Endpunkt gibt
 * `SimulationState.to_dict()` zurueck (backend/app/api/simulation_profiles.py:65
 * ueber `json_success`, Felder in `services/simulation_manager.py:94`).
 * Die frueheren Felder `branch_id`/`parent_simulation_id` existierten dort
 * nie; die Herkunft steht in `source_simulation_id`/`root_simulation_id`.
 */
export interface BranchRecord {
  simulation_id: string
  project_id: string
  graph_id: string
  status: string
  branch_name: string | null
  source_simulation_id: string | null
  root_simulation_id: string | null
  profiles_count: number
  created_at?: string
  updated_at?: string
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
export const createSimulation = (data: CreateSimulationData): Promise<ApiEnvelope<SimulationRecord>> => {
  return service.post('/api/simulation/create', data)
}

/**
 * Prepare simulation environment (async task)
 * @param data - { simulation_id, entity_types?, use_llm_for_profiles?, parallel_profile_count?, force_regenerate? }
 */
export const prepareSimulation = (data: PrepareSimulationData): Promise<ApiEnvelope<TaskStatusData>> => {
  return service.post('/api/simulation/prepare', data)
}

/**
 * Query prepare task progress
 * @param data - { task_id?, simulation_id? }
 */
export const getPrepareStatus = (data: TaskStatusData): Promise<ApiEnvelope<TaskStatusData>> => {
  return service.post('/api/simulation/prepare/status', data)
}

/**
 * Get simulation status
 * @param simulationId
 */
export const getSimulation = (simulationId: string): Promise<ApiEnvelope<SimulationRecord>> => {
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
): Promise<ApiEnvelope<ProfileRecord[]>> => {
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
): Promise<ApiEnvelope<ProfilesRealtimeResponse>> => {
  return service.get(`/api/simulation/${simulationId}/profiles/realtime`, { params: { platform } })
}

/**
 * Get simulation configuration
 * @param simulationId
 */
export const getSimulationConfig = (simulationId: string): Promise<ApiEnvelope<Record<string, unknown>>> => {
  return service.get(`/api/simulation/${simulationId}/config`)
}

/**
 * Get simulation configuration being generated in real-time
 * @param simulationId
 * @returns Returns configuration information containing metadata and config content
 */
export const getSimulationConfigRealtime = (
  simulationId: string
): Promise<ApiEnvelope<ConfigRealtimeResponse>> => {
  return service.get(`/api/simulation/${simulationId}/config/realtime`)
}

/**
 * List all simulations
 * @param projectId - Optional, filter by project ID
 */
export const listSimulations = (projectId?: string): Promise<ApiEnvelope<SimulationRecord[]>> => {
  const params = projectId ? { project_id: projectId } : {}
  return service.get('/api/simulation/list', { params })
}

/**
 * Start simulation
 * @param data - { simulation_id, platform?, max_rounds?, simulation_days?, enable_graph_memory_update? }
 */
export const startSimulation = (data: StartSimulationData): Promise<ApiEnvelope<RunStatusResponse>> => {
  return service.post('/api/simulation/start', data)
}

/**
 * Stop simulation
 * @param data - { simulation_id }
 */
export const stopSimulation = (data: StopSimulationData): Promise<ApiEnvelope<RunStatusResponse>> => {
  return service.post('/api/simulation/stop', data)
}

/**
 * Get simulation real-time run status
 * @param simulationId
 */
export const getRunStatus = (simulationId: string): Promise<ApiEnvelope<RunStatusResponse>> => {
  return service.get(`/api/simulation/${simulationId}/run-status`)
}

/**
 * Get simulation detailed run status (including recent actions)
 * @param simulationId
 */
export const getRunStatusDetail = (simulationId: string): Promise<ApiEnvelope<RunStatusResponse>> => {
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
): Promise<ApiEnvelope<unknown[]>> => {
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
): Promise<ApiEnvelope<TimelineResponse>> => {
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
export const getAgentStats = (simulationId: string): Promise<ApiEnvelope<AgentStatsResponse>> => {
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
): Promise<ApiEnvelope<unknown[]>> => {
  return service.get(`/api/simulation/${simulationId}/actions`, { params })
}

/**
 * Close simulation environment (graceful shutdown)
 * @param data - { simulation_id, timeout? }
 */
export const closeSimulationEnv = (data: CloseEnvData): Promise<ApiEnvelope<unknown>> => {
  return service.post('/api/simulation/close-env', data)
}

/**
 * Get simulation environment status
 * @param data - { simulation_id }
 */
export const getEnvStatus = (data: EnvStatusData): Promise<ApiEnvelope<unknown>> => {
  return service.post('/api/simulation/env-status', data)
}

/**
 * Batch interview Agents
 * @param data - { simulation_id, interviews: [{ agent_id, prompt }] }
 */
export const interviewAgents = (data: InterviewAgentsData): Promise<ApiEnvelope<unknown>> => {
  return service.post('/api/simulation/interview/batch', data)
}

/**
 * Get simulation history list (with project details)
 * Used to display historical projects on home page
 * @param limit - Return count limit
 */
export const getSimulationHistory = (limit = 20): Promise<ApiEnvelope<SimulationRecord[]>> => {
  return service.get('/api/simulation/history', { params: { limit } })
}

/**
 * List installed Ollama + curated LLM model presets for the model dropdown.
 */
export const getAvailableModels = (): Promise<ApiEnvelope<AvailableModelsResponse>> => {
  return service.get('/api/simulation/available-models')
}

/**
 * Pause a running simulation between rounds.
 */
export const pauseSimulation = (simulationId: string): Promise<ApiEnvelope<RunStatusResponse>> => {
  return service.post(`/api/simulation/${simulationId}/pause`)
}

/**
 * Resume a paused simulation.
 */
export const resumeSimulation = (simulationId: string): Promise<ApiEnvelope<RunStatusResponse>> => {
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
): Promise<ApiEnvelope<{ lines: string[]; from_line: number; total_lines: number }>> => {
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
): Promise<ApiEnvelope<ProfileRecord>> => {
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
): Promise<ApiEnvelope<unknown>> => {
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
): Promise<ApiEnvelope<ProfileRecord>> => {
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
): Promise<ApiEnvelope<ProfileRecord>> => {
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
): Promise<ApiEnvelope<ProfileRecord>> => {
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
): Promise<ApiEnvelope<ProfileRecord>> => {
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
): Promise<ApiEnvelope<ProfileQualityResponse>> => {
  return service.get(`/api/simulation/${simulationId}/profiles/quality`)
}

/**
 * List reusable persona templates stored on the local backend.
 *
 * Der Response-Interceptor (api/index.ts) gibt die ENVELOPE zurueck, nicht
 * deren `data`. Der frueher deklarierte Typ `PersonaTemplateRecord[]` war
 * darum optimistisch — jeder Aufrufer musste ihn wegcasten, und wer das
 * vergass, griff ins Leere (Block B3).
 */
export const listPersonaTemplates = (): Promise<
  ApiEnvelope<{ count: number; templates: PersonaTemplateRecord[] }>
> => {
  return service.get('/api/simulation/persona-library')
}

/**
 * Save a generated or manually authored persona as a reusable template.
 * @param data
 */
export const savePersonaTemplate = (
  data: PersonaTemplateRecord
): Promise<ApiEnvelope<PersonaTemplateRecord>> => {
  return service.post('/api/simulation/persona-library', data)
}

/**
 * Delete a reusable persona template.
 * @param templateId
 */
export const deletePersonaTemplate = (templateId: string): Promise<ApiEnvelope<unknown>> => {
  return service.delete(`/api/simulation/persona-library/${encodeURIComponent(templateId)}`)
}

/**
 * POST /api/simulation/<id>/branch — Simulation aus einer bestehenden
 * ableiten. Der Interceptor gibt die Envelope zurueck, nicht ihr `data`
 * (siehe api/index.ts) — der Typ sagt das jetzt auch. Vorher stand hier
 * `Promise<BranchRecord>`, und jeder Aufrufer musste das wegcasten.
 */
/**
 * POST /api/simulation/create-from-personas — Lauf allein aus
 * gespeicherten Personas (Block B4). Kein Dokument, kein Graph.
 */
export const createSimulationFromPersonas = (data: {
  simulation_requirement: string
  template_ids?: string[]
  personas?: Record<string, unknown>[]
}): Promise<ApiEnvelope<{ simulation_id: string; project_id: string; persona_count: number }>> => {
  return service.post('/api/simulation/create-from-personas', data)
}

export const createSimulationBranch = (
  simulationId: string,
  data: BranchData
): Promise<ApiEnvelope<BranchRecord>> => {
  return service.post(`/api/simulation/${simulationId}/branch`, data)
}

export const listSimulationBranches = (
  simulationId: string
): Promise<ApiEnvelope<BranchRecord[]>> => {
  return service.get(`/api/simulation/${simulationId}/branches`)
}
