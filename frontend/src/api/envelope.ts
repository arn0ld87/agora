/**
 * Envelope-Mapper für die standardisierte Backend-Response-Form.
 *
 * Backend liefert seit EPIC-09 Sub-Slice 1 für jede `/api/*`-Antwort:
 *   Success: `{success: true, data: T, count?, message?, meta?}`
 *   Error:   `{success: false, code: ApiErrorCode, error: string, details?}`
 *
 * `unwrap` kapselt das Auspacken; bei Error wirft es `ApiError` mit `code`,
 * sodass die UI semantisch reagieren kann (z.B. `service_unavailable` →
 * "Backend offline" mit Retry-Button) statt nur generische `Error.message`-
 * Strings rauszufischen.
 */

export interface ApiSuccessEnvelope<T> {
  success: true
  data: T
  count?: number
  message?: string
  meta?: Record<string, unknown>
}

export interface ApiErrorEnvelope {
  success: false
  code?: string
  error: string
  details?: Record<string, unknown>
  /** Backend ergänzt sporadisch zusätzliche Top-Level-Felder (z.B. `task_id`). */
  [key: string]: unknown
}

export type ApiEnvelope<T> = ApiSuccessEnvelope<T> | ApiErrorEnvelope

export interface ApiErrorOptions {
  code: string
  status: number
  message: string
  details?: Record<string, unknown>
  originalResponse?: unknown
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details?: Record<string, unknown>
  readonly originalResponse?: unknown

  constructor(opts: ApiErrorOptions) {
    super(opts.message)
    this.name = 'ApiError'
    this.code = opts.code
    this.status = opts.status
    this.details = opts.details
    this.originalResponse = opts.originalResponse
    // Damit `instanceof ApiError` über transpilierte Targets verlässlich bleibt.
    Object.setPrototypeOf(this, ApiError.prototype)
  }
}

/**
 * Auspack-Helper: bei Erfolg gibt es `data` direkt zurück, bei Error wirft
 * es `ApiError` mit `code` aus dem Envelope. Komponenten, die noch nicht
 * migriert sind, können weiter `res.data` lesen — `unwrap` ist additiv.
 */
export function unwrap<T>(envelope: ApiEnvelope<T>): T {
  if (envelope && envelope.success === true) {
    return envelope.data
  }
  const errEnv = envelope as ApiErrorEnvelope
  throw new ApiError({
    code: errEnv?.code || 'unknown_error',
    status: 0,
    message: errEnv?.error || 'Unbekannter Fehler',
    details: errEnv?.details,
    originalResponse: envelope,
  })
}

/** Type-Guard für UI-Code, der je nach Fehlerquelle reagieren muss. */
export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}
