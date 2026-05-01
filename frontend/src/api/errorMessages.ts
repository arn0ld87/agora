/**
 * Frontend-Mapping `ApiErrorCode` → benutzerfreundliche deutsche Toast-Texte.
 *
 * Spiegelt `backend/app/utils/api_errors.py::DEFAULT_MESSAGES`, aber bewusst
 * UI-zentriert formuliert (mehr Kontext, "bitte erneut versuchen", Hinweise
 * auf Folgeschritte). Die Backend-Defaults sind API-Defaults, die hier sind
 * UX-Defaults.
 */

import type { ApiError } from './envelope'

/** UI-Texte; Schlüssel = `ApiErrorCode`-Wert (siehe Backend-Katalog). */
export const ERROR_MESSAGES: Record<string, string> = {
  invalid_id: 'Ungültige ID — bitte erneut prüfen',
  not_found: 'Eintrag nicht gefunden',
  validation_failed: 'Eingabe ungültig — bitte Werte prüfen',
  bad_request: 'Anfrage ungültig',
  method_not_allowed: 'Methode nicht erlaubt',

  auth_required: 'Anmeldung erforderlich',
  auth_invalid: 'Anmeldung ungültig — bitte neu einloggen',
  auth_forbidden: 'Zugriff verweigert',

  rate_limited: 'Zu viele Anfragen — bitte später erneut versuchen',
  timeout: 'Zeitüberschreitung — Backend antwortet zu langsam',

  service_unavailable: 'Backend offline oder nicht erreichbar',
  neo4j_unavailable: 'Datenbank (Neo4j) nicht erreichbar',
  llm_unavailable: 'LLM-Endpunkt nicht erreichbar',

  ontology_missing: 'Ontologie fehlt — bitte zuerst generieren',
  ontology_generation_failed: 'Ontologie-Generierung fehlgeschlagen — erneut versuchen',

  simulation_not_prepared: 'Simulation noch nicht vorbereitet — Schritt /prepare ausführen',
  simulation_already_running: 'Simulation läuft bereits',
  persona_review_required: 'Persona-Review erforderlich, bevor die Simulation startet',

  upload_too_large: 'Datei zu groß',
  unsupported_format: 'Format nicht unterstützt',

  internal_error: 'Interner Serverfehler',
  not_implemented: 'Funktion noch nicht verfügbar',

  graph_build_in_progress: 'Graph-Build läuft bereits — bitte warten',
}

/** Fehler, bei denen ein Retry sinnvoll ist (transient / Infrastruktur). */
const RETRYABLE_CODES: ReadonlySet<string> = new Set([
  'service_unavailable',
  'neo4j_unavailable',
  'llm_unavailable',
  'rate_limited',
  'timeout',
  'ontology_generation_failed',
])

export function userMessageFor(error: ApiError): string {
  return ERROR_MESSAGES[error.code] || error.message || 'Unbekannter Fehler'
}

export function isRetryable(error: ApiError): boolean {
  return RETRYABLE_CODES.has(error.code)
}
