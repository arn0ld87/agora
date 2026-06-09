/**
 * Issue #578/#585 — Typed parse helpers for API envelope unwrapping.
 *
 * #578: Replaces bare `.parse()` callsites with safeParse + typed rejection,
 * so schema drift becomes a catchable error instead of an unhandled rejection.
 *
 * #585: Adds `unwrapResponse<T>` as a standalone envelope-unwrap helper,
 * replacing inline envelope-cast patterns across API modules.
 */
import type { ZodSchema } from 'zod'

/**
 * Unwraps the `data` field from an API response envelope.
 * Falls back to `resp` itself when the envelope has no `data` field (e.g.
 * already-unwrapped payloads, endpoints that return bare objects like
 * `cancelRun`).  Mirrors the tolerant behaviour of `unwrapAndParse` (#607).
 *
 * Use this when you want the raw data without schema validation, or when
 * calling code handles validation separately.
 *
 * @param resp - The raw value returned by the axios service.
 */
export function unwrapResponse<T>(resp: unknown): T {
  return (
    resp !== null && typeof resp === 'object' && 'data' in resp
      ? (resp as { data: unknown }).data
      : resp
  ) as T
}

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
