/**
 * Schmale Zod-Hülle für die Antworten der Simulationssteuerung (#1801, Ticket D).
 * Jede Antwort läuft durch `safeParse`; `success=false` und Vertragsbrüche
 * werden zu einem Fehler mit dem Backend-Text, nie zu stillem Weiterrendern.
 */
import { z } from 'zod'

const EnvelopeSchema = z
  .object({
    success: z.boolean(),
    error: z.string().nullish(),
    message: z.string().nullish(),
    data: z.unknown().optional(),
  })
  .passthrough()

export function readEnvelope<S extends z.ZodType>(raw: unknown, data: S, label: string): z.infer<S> {
  const env = EnvelopeSchema.safeParse(raw)
  if (!env.success) throw new Error(`Vertragsbruch ${label}: ${env.error.message}`)
  if (!env.data.success) throw new Error(env.data.error || env.data.message || `${label}: unknown`)
  const parsed = data.safeParse(env.data.data)
  if (!parsed.success) throw new Error(`Vertragsbruch ${label}: ${parsed.error.message}`)
  return parsed.data
}

export function describeError(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return String(err)
}
