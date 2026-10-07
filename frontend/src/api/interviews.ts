/**
 * Interviews am Lauf (#1805, Etappe 6): Fragen an Personas und Verlauf.
 * Jede Antwort läuft durch ein Zod-Schema (`contracts/interviewContract`).
 *
 * Fehlerbild des Backends (`backend/app/api/simulation_interviews.py`):
 * - `batch` antwortet auch bei fachlichen Fehlern mit HTTP 200 und
 *   `success:false`; das wird hier zu einem `ApiError` (Status 200, Code des
 *   Backends), den `interviewErrorMessage` richtig einordnet.
 * - `success:true` heißt nur: mindestens eine Antwort kam. Fehler je Persona
 *   stehen im Eintrag und bleiben dort erhalten (`InterviewAnswer.error`).
 * - 503, wenn weder die Umgebung lebt noch persistierte Personas vorliegen.
 * `interviewAgents` in `api/simulation.ts` bleibt für die Altansicht bestehen.
 */
import service from './index'
import { ApiError } from './envelope'
import { readEnvelope } from '@/composables/run/simulation/simulationEnvelope'
import {
  InterviewBatchDataSchema,
  InterviewHistoryDataSchema,
  type InterviewHistoryItem,
} from '@/contracts/interviewContract'

export interface InterviewQuestion {
  agentId: number
  prompt: string
  /** Ohne Angabe befragt das Backend nur eine Plattform (Reddit bevorzugt). */
  platform?: 'twitter' | 'reddit'
}

export interface InterviewAnswer {
  agentId: number
  platform: string | null
  prompt: string | null
  /** `null`, wenn keine Antwort kam; dann steht der Grund in `error`. */
  response: string | null
  timestamp: string | null
  error: string | null
}

export interface AskOptions {
  /** Frist des Backends in Sekunden (Standard dort: 120 s für Batch). */
  timeout?: number
}

export interface HistoryQuery {
  agentId?: number
  platform?: 'twitter' | 'reddit'
  limit?: number
}

/** Hebt `success:false` bei HTTP 200 zu einem sichtbaren Fehler samt Backend-Code. */
function assertSuccess(raw: unknown): void {
  if (typeof raw === 'object' && raw !== null && (raw as { success?: unknown }).success === false) {
    const env = raw as { code?: unknown; error?: unknown; message?: unknown }
    throw new ApiError({
      code: typeof env.code === 'string' && env.code ? env.code : 'unknown_error',
      status: 200,
      message:
        (typeof env.error === 'string' && env.error) ||
        (typeof env.message === 'string' && env.message) ||
        'Interview fehlgeschlagen',
      originalResponse: raw,
    })
  }
}

export async function askPersonas(
  simulationId: string,
  questions: readonly InterviewQuestion[],
  options: AskOptions = {},
): Promise<InterviewAnswer[]> {
  const body: Record<string, unknown> = {
    simulation_id: simulationId,
    interviews: questions.map((q) => ({
      agent_id: q.agentId,
      prompt: q.prompt,
      ...(q.platform ? { platform: q.platform } : {}),
    })),
  }
  if (options.timeout !== undefined) body.timeout = options.timeout
  const raw: unknown = await service.post('/api/simulation/interview/batch', body)
  assertSuccess(raw)
  const data = readEnvelope(raw, InterviewBatchDataSchema, 'interview/batch')
  return Object.values(data.result.results).map((e) => ({
    agentId: e.agent_id,
    platform: e.platform ?? null,
    prompt: e.prompt ?? null,
    response: e.response ?? null,
    timestamp: e.timestamp ?? null,
    error: e.error ?? null,
  }))
}

export async function getInterviewHistory(
  simulationId: string,
  query: HistoryQuery = {},
): Promise<InterviewHistoryItem[]> {
  const body: Record<string, unknown> = { simulation_id: simulationId }
  if (query.agentId !== undefined) body.agent_id = query.agentId
  if (query.platform) body.platform = query.platform
  if (query.limit !== undefined) body.limit = query.limit
  const raw: unknown = await service.post('/api/simulation/interview/history', body)
  assertSuccess(raw)
  return readEnvelope(raw, InterviewHistoryDataSchema, 'interview/history').history
}
