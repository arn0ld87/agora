import { isApiError } from '../api/envelope'

/**
 * Fehlertext fuer das Direkt-Interview (Einzel-Chat + Survey/Batch) in
 * `Step5Interaction.vue`.
 *
 * Issue #1000: beide `catch`-Bloecke wrappten jeden Fehler unbesehen mit
 * `errors.network`, ohne `status`/`code` anzusehen. Ein HTTP-400
 * ("Please pass a valid API key") landete damit als "Netzwerkfehler.
 * Server erreichbar?" — die Diagnose zeigte in die falsche Richtung.
 *
 * Klassifizierung anhand `ApiError.status` (siehe `../api/envelope`):
 *   - 401/403        -> Authentifizierungs-/Berechtigungsfehler
 *   - uebrige 4xx     -> Anfragefehler des Backends (Backend-`message` bleibt sichtbar,
 *                        sie traegt die eigentliche Ursache)
 *   - 5xx            -> Serverfehler
 *   - 200 (Envelope-Fehler, `success: false` in einer 200er-Huelle)
 *                     -> KEIN Netzwerkfehler. `_echo_result` im Backend
 *                        (`backend/app/api/simulation_interviews.py`) antwortet
 *                        bei fachlichen Interview-Fehlern bewusst mit HTTP 200;
 *                        die tatsaechliche Ursache steht in `ApiError.message`
 *                        (top-level `error` im Envelope). Klassifizierung anhand
 *                        `ApiError.code`, falls er einen Auth-/Berechtigungsfehler
 *                        bezeichnet, sonst als Anfragefehler.
 *   - kein `status` / `status === 0` (Transportfehler, Timeout, Backend offline)
 *                     -> weiterhin `errors.network`
 *
 * `t` wird injiziert, damit die Funktion ohne Vue-Kontext testbar bleibt.
 */
export type TranslateFn = (key: string) => string

// Codes, die trotz HTTP 200 (Envelope-Fehler) auf einen Auth-/Berechtigungsfehler
// hindeuten. Die Werte spiegeln `ApiErrorCode` aus `backend/app/utils/api_errors.py`
// — frei erfundene Codes wuerden hier nie greifen. Liefert das Backend keinen
// `code`, gilt der Envelope-Fehler als gewoehnlicher Anfragefehler
// (`errors.requestError`); die Backend-Meldung bleibt dabei sichtbar.
const AUTH_ERROR_CODES = new Set(['auth_required', 'auth_invalid', 'auth_forbidden'])

function messageOf(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

function isAuthCode(code: string | undefined): boolean {
  return typeof code === 'string' && AUTH_ERROR_CODES.has(code)
}

export function interviewErrorMessage(err: unknown, t: TranslateFn): string {
  const message = messageOf(err)
  const status = isApiError(err) ? err.status : undefined
  const code = isApiError(err) ? err.code : undefined

  if (status === 401 || status === 403) {
    return `(${t('errors.authError')}: ${message})`
  }
  if (typeof status === 'number' && status >= 400 && status < 500) {
    return `(${t('errors.requestError')}: ${message})`
  }
  if (typeof status === 'number' && status >= 500) {
    return `(${t('errors.serverError')}: ${message})`
  }
  if (status === 200) {
    if (isAuthCode(code)) {
      return `(${t('errors.authError')}: ${message})`
    }
    return `(${t('errors.requestError')}: ${message})`
  }
  return `(${t('errors.network')}: ${message})`
}
