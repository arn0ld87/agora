/**
 * Issue #578 — Typed parse helper for LLM API modules.
 *
 * Replaces bare `.parse()` callsites with safeParse + typed rejection,
 * so schema drift becomes a catchable error instead of an unhandled rejection.
 */
import type { ZodSchema } from 'zod'

/**
 * Unwraps the `data` field from an axios response envelope and validates it
 * against `schema` via `safeParse`. Throws a typed `Error` on schema drift
 * instead of letting ZodError bubble as an unhandled rejection.
 *
 * @param resp   - The raw value returned by the axios service (already the
 *                 envelope body, i.e. `{ success, data, ... }`).
 * @param schema - Zod schema to validate `resp.data` against.
 */
export function unwrapAndParse<T>(resp: unknown, schema: ZodSchema<T>): T {
  // Tolerant unwrap: if resp is an object with a `data` key, use that field;
  // otherwise fall back to resp itself (handles already-unwrapped responses).
  const data =
    resp !== null && typeof resp === 'object' && 'data' in resp
      ? (resp as { data?: unknown }).data
      : resp
  const parsed = schema.safeParse(data)
  if (!parsed.success) {
    console.warn('[api] envelope parse failed', parsed.error.flatten())
    throw new Error(`schema mismatch: ${parsed.error.message}`)
  }
  return parsed.data
}
