/**
 * Protokoll-Hilfen (Aktivität, #1797): Zod-Prüfung der Tail-Antwort von
 * `GET /api/logs` und der Strom-Frames von `/api/logs/stream`, dazu der
 * Lauf-Filter der Konsole.
 *
 * Der Lauf-Filter ist eine reine Textsuche: `/api/logs/stream` und
 * `/api/logs` kennen nur `level`, `tail` und `offset`, keinen Filter nach
 * Simulation. Eine Zeile gilt als zum Lauf gehörend, wenn ihr Text die
 * Kennung enthält. Das ist nicht exakt.
 */
import { z } from 'zod'

const TailDataSchema = z.object({
  lines: z.array(z.string()).default(() => []),
  offset: z.number().optional(),
  file: z.string().nullable().optional(),
  message: z.string().optional(),
})
export type LogTailData = z.infer<typeof TailDataSchema>

const EnvelopeSchema = z.object({ success: z.boolean(), data: z.unknown().optional(), error: z.string().optional() })

export type LogTailResult =
  | { ok: true; data: LogTailData }
  | { ok: false; error: string | null }

/**
 * Der Axios-Interceptor liefert die Hülle `{success, data}`; ältere Aufrufer
 * reichten sie ein zweites Mal als `{data: {success, data}}` durch. Beide
 * Formen werden akzeptiert, jede andere ist ein Fehler.
 */
export function parseLogTail(res: unknown): LogTailResult {
  const direct = EnvelopeSchema.safeParse(res)
  const inner = direct.success
    ? direct
    : EnvelopeSchema.safeParse((res as { data?: unknown } | null)?.data)
  if (!inner.success) return { ok: false, error: null }
  if (!inner.data.success) return { ok: false, error: inner.data.error ?? null }
  const data = TailDataSchema.safeParse(inner.data.data ?? {})
  return data.success ? { ok: true, data: data.data } : { ok: false, error: null }
}

const FrameSchema = z.object({ line: z.string() })

/** Zeile aus einem SSE-Frame, `null` bei allem, was keine Protokollzeile ist. */
export function parseLogFrame(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  try {
    const parsed = FrameSchema.safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data.line : null
  } catch {
    return null
  }
}

/** Nur Zeilen, deren Text die Kennung enthält (Textsuche, nicht exakt). */
export function filterLinesByScope(lines: readonly string[], scopeId: string | null): string[] {
  if (!scopeId) return [...lines]
  return lines.filter((ln) => typeof ln === 'string' && ln.includes(scopeId))
}
