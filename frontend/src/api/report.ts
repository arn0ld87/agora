import service, { requestWithRetry } from './index'
import type { ApiEnvelope } from './envelope'
import type { LlmRuntimePayload } from './llmRuntime'
import type { Report, EvidenceMap, ReportSection, EvidenceItem } from '../contracts/reportContract'
import type { ReportMode } from '../contracts/reportV3Contract'
import type { AiModelRef } from '../contracts/aiModelRef'

// --- Local payload/data types -------------------------------------------
// These describe the `data` field inside the API envelope, not the envelope itself.

/** Explizite (Connection, Modell)-Auswahl aus dem Report-Picker (Issue #817).
 * Direkt vom kanonischen `AiModelRef` abgeleitet, damit die Enum-Constraint auf
 * `source` erhalten bleibt und kein Parallel-Contract entsteht.
 *
 * `fallback_reason` reist mit (Issue #901). `AiModelPicker` kennt bei einer
 * Fallback-Auswahl sehr wohl einen Grund — `unknown_provider` bei unbekannter
 * Item-ID, `provider_offline` bei `status: 'unavailable'`, `provider_degraded`
 * bei `status: 'degraded'`. Ohne das Feld verwarfen die Request-Builder genau
 * diese Diagnose, und `llm_routing_seed._fallback_reason_for` schrieb den
 * Platzhalter `unspecified_fallback` in die Route — der Grund wäre nur
 * scheinbar unbekannt gewesen. Der Platzhalter bleibt als Netz fuer die Faelle,
 * in denen wirklich kein Grund ableitbar ist. */
export type AiModelRefPayload = Pick<
  AiModelRef,
  'provider_connection_id' | 'model_id' | 'source'
> & {
  fallback_reason?: string | null
}

export interface GenerateReportData {
  simulation_id: string
  force_regenerate?: boolean
  /** Legacy-Kompatibilität; bei gesetztem `ai_model_ref` nicht mitsenden. */
  llm_model?: string
  llm_provider?: LlmRuntimePayload
  /** Legacy-Kompatibilität; bei gesetztem `ai_model_ref` nicht mitsenden. */
  llm_profile_id?: string
  /** Autoritative UI-Auswahl. Darf nicht mit den Legacy-Feldern kombiniert werden. */
  ai_model_ref?: AiModelRefPayload
  /** Report-Modus — wird als ?mode=<value> Query-Parameter übergeben (Backend: request.args.get("mode")). */
  mode?: ReportMode
  [key: string]: unknown
}

export interface ReportStatusParams {
  simulationId?: string
  taskId?: string
  reportId?: string
}

export interface ReportStatusData {
  task_id?: string
  status: string
  progress?: number
  message?: string
  report_id?: string
  simulation_id?: string
  error?: string | null
  outline?: unknown
  sections?: Record<string, unknown>
  current_section_index?: number | null
}

/** Shape expected by useIncrementalLogPolling's fetcher contract. */
export interface LogEnvelope {
  success?: boolean
  data?: {
    lines?: unknown[]
    logs?: unknown[]
    next_line?: number
    total_lines?: number
  }
}

export interface ChatWithReportData {
  simulation_id: string
  message: string
  chat_history?: Array<{ role: string; content: string }>
}

export interface ChatData {
  reply: string
  [key: string]: unknown
}

// --- API functions -------------------------------------------------------
// Return types are ApiEnvelope<T> because the index.ts response interceptor
// returns response.data (the full envelope) unchanged for success: true cases.

/**
 * Start report generation.
 * @param data - { simulation_id, force_regenerate?, llm_model?, mode? }
 *
 * Das Backend liest `mode` als Query-Parameter (?mode=strict|balanced|explorative),
 * alle anderen Felder kommen als JSON-Body.
 *
 * Issue #579: timeout: 0 disables the global 5-min cap for this long-running endpoint.
 * Report generation can take 10–30 min; the global axios timeout would abort it at 5 min.
 */
export const generateReport = (
  data: GenerateReportData | Record<string, unknown>
): Promise<ApiEnvelope<ReportStatusData>> => {
  const { mode, ...body } = data as GenerateReportData
  const params: Record<string, string> = {}
  if (mode) params['mode'] = mode
  return requestWithRetry(
    () => service.post('/api/report/generate', body, { params, timeout: 0 }),
    3,
    1000
  )
}

/**
 * Get report generation status
 * Backend accepts POST with { task_id } or { simulation_id } or { report_id }.
 * @param params - { simulationId?, taskId?, reportId? }
 */
export const getReportStatus = ({
  simulationId,
  taskId,
  reportId,
}: ReportStatusParams = {}): Promise<ApiEnvelope<ReportStatusData>> => {
  const body: Record<string, string> = {}
  if (simulationId) body['simulation_id'] = simulationId
  if (taskId) body['task_id'] = taskId
  if (reportId) body['report_id'] = reportId
  return service.post('/api/report/generate/status', body)
}

/**
 * Get Agent log (incremental)
 * @param reportId
 * @param fromLine - Start from which line
 */
export const getAgentLog = (
  reportId: string,
  fromLine = 0
): Promise<LogEnvelope> => {
  return service.get(`/api/report/${reportId}/agent-log`, { params: { from_line: fromLine } })
}

/**
 * Get console log (incremental)
 * @param reportId
 * @param fromLine - Start from which line
 */
export const getConsoleLog = (
  reportId: string,
  fromLine = 0
): Promise<LogEnvelope> => {
  return service.get(`/api/report/${reportId}/console-log`, { params: { from_line: fromLine } })
}

/**
 * Get report details
 * @param reportId
 */
export const getReport = (reportId: string): Promise<ApiEnvelope<Report>> => {
  return service.get(`/api/report/${reportId}`)
}

export const getReportEvidence = (reportId: string): Promise<ApiEnvelope<EvidenceMap>> => {
  return service.get(`/api/report/${reportId}/evidence`)
}

export const getReportEvidenceSection = (
  reportId: string,
  sectionIndex: number
): Promise<ApiEnvelope<ReportSection>> => {
  return service.get(`/api/report/${reportId}/evidence/${sectionIndex}`)
}

export const getReportEvidenceClaim = (
  reportId: string,
  sectionIndex: number,
  claimId: string
): Promise<ApiEnvelope<EvidenceItem>> => {
  return service.get(`/api/report/${reportId}/evidence/${sectionIndex}/${claimId}`)
}

/**
 * Combined report export (Slice 5.1).
 * @param reportId
 * @param format
 * @returns Blob response
 */
export const exportReport = (
  reportId: string,
  format: 'md' | 'json' = 'json'
): Promise<Blob> => {
  return service.get(`/api/report/${reportId}/export`, {
    params: { format },
    responseType: 'blob',
  })
}

/**
 * CSV-Export einer strukturierten Tabelle (Sub-Slice P4.2).
 * @param reportId
 * @param table - 'personas' | 'segments' | 'claims'
 * @returns Blob mit text/csv-Inhalt
 */
export const fetchReportCsv = (
  reportId: string,
  table: 'personas' | 'segments' | 'claims'
): Promise<Blob> => {
  return service.get(`/api/report/${reportId}/export`, {
    params: { format: 'csv', table },
    responseType: 'blob',
  })
}

/**
 * ZIP-Bundle-Export aller Report-Artefakte (Sub-Slice P4.3).
 * Enthält report-v3.md, report-v3.json, evidence-map.json,
 * personas.csv, segments.csv, claims.csv — serverseitig gebaut,
 * kein jszip-Install nötig.
 * @param reportId
 * @returns Blob mit application/zip-Inhalt
 */
export const fetchReportBundle = (reportId: string): Promise<Blob> => {
  return service.get(`/api/report/${reportId}/export`, {
    params: { format: 'zip' },
    responseType: 'blob',
  })
}

/**
 * Chat with Report Agent
 * @param data - { simulation_id, message, chat_history? }
 */
export const chatWithReport = (data: ChatWithReportData): Promise<ApiEnvelope<ChatData>> => {
  return requestWithRetry(() => service.post('/api/report/chat', data), 3, 1000)
}
