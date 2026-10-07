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
