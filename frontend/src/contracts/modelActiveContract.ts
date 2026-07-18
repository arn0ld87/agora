/**
 * ModelActiveEvent-Contract — Zod-Spiegel zu backend/app/services/model_event_bus.py.
 *
 * Spiegelt ModelActiveEvent (Pydantic v2, extra="forbid").
 * Slice E.2, Issue #213.
 */
import { z } from 'zod'

export const ModelContextSchema = z.enum([
  'chat',
  'chat_json',
  'embedding',
  'report',
  'persona',
  'graph',
  'unknown',
])
export type ModelContext = z.infer<typeof ModelContextSchema>

export const ModelProviderSchema = z.enum(['ollama', 'cloud', 'minimax', 'openai', 'unknown'])
export type ModelProvider = z.infer<typeof ModelProviderSchema>

export const ModelActiveEventSchema = z
  .object({
    model: z.string().min(1),
    context: ModelContextSchema,
    provider: ModelProviderSchema,
    ts: z.number(),
    extra: z.record(z.string(), z.unknown()).nullable(),
  })
  .strict()

export type ModelActiveEvent = z.infer<typeof ModelActiveEventSchema>

export function parseModelActiveEvent(
  raw: unknown,
): { ok: true; data: ModelActiveEvent } | { ok: false; errors: z.ZodIssue[] } {
  const result = ModelActiveEventSchema.safeParse(raw)
  return result.success
    ? { ok: true, data: result.data }
    : { ok: false, errors: result.error.issues }
}
