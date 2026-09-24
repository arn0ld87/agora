import { z } from 'zod'

/**
 * Task-Status — Zod-Spiegel zu
 * `backend/app/contracts/task_status_contract.py::TaskStatusResponse`
 * (generiert nach `schemas/task-status-response.schema.json`, Issue #1466).
 *
 * Item-Form fuer `GET /api/graph/task/<task_id>` (ein Item) und
 * `GET /api/graph/tasks` (Liste desselben Shapes je Element) — Spiegel von
 * `Task.to_dict()` in `app/models/task.py`.
 *
 * `message_key` ist additiv seit #1458: aeltere Consumer, die das Feld nicht
 * kennen, lesen weiterhin `message` als menschenlesbaren Fallback.
 */

export const TaskStatusValueSchema = z.enum(['pending', 'processing', 'completed', 'failed'])
export type TaskStatusValue = z.infer<typeof TaskStatusValueSchema>

export const TaskStatusResponseSchema = z
  .object({
    task_id: z.string(),
    task_type: z.string(),
    status: TaskStatusValueSchema,
    created_at: z.string(),
    updated_at: z.string(),
    progress: z.number().int(),
    message: z.string(),
    message_key: z.string().nullable().optional(),
    progress_detail: z.record(z.string(), z.unknown()).default({}),
    result: z.record(z.string(), z.unknown()).nullable().optional(),
    error: z.string().nullable().optional(),
    metadata: z.record(z.string(), z.unknown()).default({}),
  })
  .strict()

export type TaskStatusResponse = z.infer<typeof TaskStatusResponseSchema>

/**
 * Tolerant beim Lesen, analog `parseReportStatusResponse`: ein unerwartetes
 * Feld darf den Aufrufer nicht kippen — er faellt bei einem Miss auf die
 * lose getypte Antwort zurueck.
 */
export function parseTaskStatusResponse(value: unknown): TaskStatusResponse | null {
  const result = TaskStatusResponseSchema.safeParse(value)
  return result.success ? result.data : null
}
