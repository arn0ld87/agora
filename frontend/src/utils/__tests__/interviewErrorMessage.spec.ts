import { describe, it, expect } from 'vitest'

import { ApiError, isApiError } from '../../api/envelope'
import service from '../../api/index'
import { interviewErrorMessage } from '../interviewErrorMessage'

// Stub-Uebersetzer: gibt den Key selbst zurueck, damit Assertions ohne
// echtes i18n-Setup pruefen koennen, welcher Key ausgewaehlt wurde.
const t = (key: string) => key

describe('interviewErrorMessage', () => {
  it('klassifiziert HTTP 401 als Authentifizierungsfehler', () => {
    const err = new ApiError({ code: 'unauthorized', status: 401, message: 'Ungueltige Zugangsdaten' })
    expect(interviewErrorMessage(err, t)).toBe('(errors.authError: Ungueltige Zugangsdaten)')
  })

  it('klassifiziert HTTP 403 als Authentifizierungsfehler', () => {
    const err = new ApiError({ code: 'forbidden', status: 403, message: 'Zugriff verweigert' })
    expect(interviewErrorMessage(err, t)).toBe('(errors.authError: Zugriff verweigert)')
  })

  it('klassifiziert HTTP 400 als Anfragefehler und behaelt die Backend-Message', () => {
    // Issue #1000: genau dieser Fall wurde zuvor faelschlich als Netzwerkfehler
    // angezeigt, obwohl das Backend die eigentliche Ursache (fehlender/ungueltiger
    // Provider-Key) bereits in der Message trug.
    const err = new ApiError({ code: 'bad_request', status: 400, message: 'Please pass a valid API key' })
    expect(interviewErrorMessage(err, t)).toBe('(errors.requestError: Please pass a valid API key)')
  })

  it('klassifiziert HTTP 500 als Serverfehler', () => {
    const err = new ApiError({ code: 'internal_error', status: 500, message: 'Interner Fehler' })
    expect(interviewErrorMessage(err, t)).toBe('(errors.serverError: Interner Fehler)')
  })

  it('faellt bei fehlendem status auf Netzwerkfehler zurueck', () => {
    const err = new Error('timeout of 30000ms exceeded')
    expect(interviewErrorMessage(err, t)).toBe('(errors.network: timeout of 30000ms exceeded)')
  })

  it('faellt bei status 0 (Transportfehler, Backend offline) auf Netzwerkfehler zurueck', () => {
    const err = new ApiError({ code: 'network_error', status: 0, message: 'Backend nicht erreichbar' })
    expect(interviewErrorMessage(err, t)).toBe('(errors.network: Backend nicht erreichbar)')
  })

  it('klassifiziert einen Envelope-Fehler (HTTP 200, success: false) NICHT als Netzwerkfehler', () => {
    // Realer Pfad aus Issue #1000: `_echo_result` im Backend antwortet bei
    // fachlichen Interview-Fehlern bewusst mit HTTP 200 (`jsonify(...)` ohne
    // Status). `code` fehlt im Envelope -> kein Auth-Code erkennbar -> Anfragefehler,
    // aber die Backend-Meldung bleibt sichtbar.
    const err = new ApiError({
      code: 'unknown_error',
      status: 200,
      message: 'Error code: 400 - Please pass a valid API key',
    })
    const result = interviewErrorMessage(err, t)
    expect(result).not.toContain('errors.network')
    expect(result).toContain('errors.requestError')
    expect(result).toContain('Error code: 400 - Please pass a valid API key')
  })

  it('klassifiziert einen Envelope-Fehler (HTTP 200) mit Auth-Code als Authentifizierungsfehler', () => {
    // Der Code muss ein echter Backend-Code aus `ApiErrorCode`
    // (backend/app/utils/api_errors.py) sein — `AUTH_ERROR_CODES` matcht nur
    // gegen diese Werte, nicht gegen frei erfundene Strings wie 'unauthorized'.
    const err = new ApiError({
      code: 'auth_invalid',
      status: 200,
      message: 'Please pass a valid API key',
    })
    expect(interviewErrorMessage(err, t)).toBe('(errors.authError: Please pass a valid API key)')
  })

  it('durchlaeuft den echten Response-Interceptor mit dem realen Backend-Envelope', async () => {
    // Beweist, dass die Klassifizierung den tatsaechlichen Codepfad trifft:
    // statt eine ApiError von Hand zu bauen, wird derselbe Success-Interceptor
    // aufgerufen, den `frontend/src/api/index.ts` auf die axios-Instanz
    // registriert (`service.interceptors.response`). Der Envelope entspricht
    // exakt dem, was `_echo_result` (backend/app/api/simulation_interviews.py)
    // bei einem fehlgeschlagenen Interview liefert: HTTP 200 mit `success: false`.
    const handlers = (
      service.interceptors.response as unknown as {
        handlers: Array<{ fulfilled: (response: unknown) => unknown } | null>
      }
    ).handlers
    const fulfilled = handlers.find((h) => h !== null)?.fulfilled
    expect(typeof fulfilled).toBe('function')

    const realBackendEnvelope = {
      success: false,
      error: 'Error code: 400 - Please pass a valid API key',
      data: { success: false },
    }

    let caught: unknown
    try {
      await fulfilled!({ data: realBackendEnvelope, status: 200 })
      throw new Error('erwartete Ablehnung ist ausgeblieben')
    } catch (err) {
      caught = err
    }

    expect(isApiError(caught)).toBe(true)
    expect((caught as ApiError).status).toBe(200)

    const result = interviewErrorMessage(caught, t)
    expect(result).not.toContain('errors.network')
    expect(result).toContain('errors.requestError')
    expect(result).toContain('Please pass a valid API key')
  })
})
