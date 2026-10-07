/**
 * Zod-Schemas der Interview-Endpunkte einer Simulation (#1805, Etappe 6).
 *
 * Spiegel der BEOBACHTETEN Form, kein generierter Vertrag: das Backend führt
 * `data` der Endpunkte `POST /api/simulation/interview/batch` und
 * `/interview/history` als offenes Dict (`backend/app/api/simulation_interviews.py`,
 * `services/sim/interview_direct.py`). Darum sind die Schemas schmal und
 * `passthrough`: geprüft wird, was die Oberfläche liest, Unbekanntes bleibt
 * stehen. Ein Bruch dieser Form wird beim Lesen als Fehler sichtbar.
 */
import { z } from 'zod'

/** `agent_id` ist die Listenposition des Profils; das Backend liefert Zahl oder Ziffernfolge. */
const AgentIdSchema = z.union([z.number().int().nonnegative(), z.string().regex(/^\d+$/)]).transform(Number)

/** Eintrag unter `result.results["<platform>_<agent_id>"]` der Batch-Antwort. */
export const InterviewBatchEntrySchema = z
  .object({
    agent_id: AgentIdSchema,
    platform: z.string().nullish(),
    prompt: z.string().nullish(),
    response: z.string().nullish(),
    timestamp: z.string().nullish(),
    simulated: z.boolean().nullish(),
    mode: z.string().nullish(),
    /** Fehler dieses einen Eintrags; die Antwort als Ganzes kann trotzdem `success` sein. */
    error: z.string().nullish(),
  })
  .passthrough()

export const InterviewBatchDataSchema = z
  .object({
    success: z.boolean().nullish(),
    interviews_count: z.number().nullish(),
    mode: z.string().nullish(),
    result: z
      .object({ results: z.record(z.string(), InterviewBatchEntrySchema) })
      .passthrough(),
    timestamp: z.string().nullish(),
  })
  .passthrough()

/** Zeile aus `POST /api/simulation/interview/history`. */
export const InterviewHistoryItemSchema = z
  .object({
    agent_id: AgentIdSchema,
    response: z.string().nullish(),
    prompt: z.string(),
    timestamp: z.string(),
    platform: z.string().nullish(),
  })
  .passthrough()

export const InterviewHistoryDataSchema = z
  .object({
    count: z.number().nullish(),
    history: z.array(InterviewHistoryItemSchema),
  })
  .passthrough()

export type InterviewBatchEntry = z.infer<typeof InterviewBatchEntrySchema>
export type InterviewBatchData = z.infer<typeof InterviewBatchDataSchema>
export type InterviewHistoryItem = z.infer<typeof InterviewHistoryItemSchema>
export type InterviewHistoryData = z.infer<typeof InterviewHistoryDataSchema>

/**
 * 409-Body `budget_exceeded` der Interview-Endpunkte. Spiegel des Backend-Vertrags
 * `InterviewBudgetExceededResponse` (`backend/app/contracts/interview_budget_exceeded_contract.py`,
 * `schemas/interview-budget-exceeded.schema.json`).
 */
export const InterviewBudgetExceededSchema = z.object({
  success: z.literal(false).default(false),
  error: z.string().min(1),
  code: z.literal('budget_exceeded').default('budget_exceeded'),
  termination_reason: z.enum([
    'completed',
    'error',
    'user_cancel',
    'user_stop',
    'budget_tokens',
    'budget_cost',
    'budget_time',
    'budget_calls',
    'process_restart',
  ]),
  dimension: z.enum(['tokens', 'cost', 'time', 'calls']),
  observed: z.number().int(),
  threshold: z.number().int(),
  /** Antworten dieses Aufrufs, die vor dem Abbruch gespeichert wurden und im Verlauf stehen. */
  persisted_count: z.number().int().nonnegative().default(0),
})
export type InterviewBudgetExceeded = z.infer<typeof InterviewBudgetExceededSchema>
