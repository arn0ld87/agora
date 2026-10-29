/**
 * reportViewState — Deep Module fuer Status-Praedikate, Envelope-Klassifikation
 * und Fehlerbehandlung des Bericht-Reiters (Slice #5).
 *
 * Konsolidiert das zuvor ueber `useRunReport.ts`, `useReportGeneration.ts`,
 * `useReportArtifacts.ts`, `reportSections.ts`, `ReportReadingPane.vue` und
 * `ReportEvidencePanel.vue` verstreute Domänenwissen:
 *  - Wann gilt ein Bericht als laufend (`pending`, `planning`, `generating`),
 *    wann als terminal mit Belegen (`completed`, `incomplete`), wann als
 *    endgültig abgeschlossen (`completed`, `incomplete`, `failed`)?
 *  - Wann beweist die Run-Registry (`run_id` + `pending`/`processing`) einen
 *    aktiven Hintergrundlauf, sodass ein 404 beim Laden des Berichts als
 *    erwartbares `idle` statt als Ladefehler gewertet wird (UAT-010)?
 *  - Wann ist ein 404 / `not_found` bei Evidence oder Artefakten `unsaved`
 *    statt `failed`?
 *  - Wann signalisiert eine Antwort `report_generate_in_progress` (409) und
 *    liefert eine laufende `report_id`, an die sich die Ansicht anhängen kann?
 */

import { ApiError } from '@/api/envelope'
import type { EvidenceEnvelope } from '@/api/report'
import {
  ReportSchema,
  type EvidenceMap,
  type EvidenceOmission,
  type Report,
} from '@/contracts/reportContract'

export type LoadFailure = { kind: 'notFound' | 'contract' | 'transport'; reason: string }

export type ReportState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; report: Report }
  | ({ status: 'failed' } & LoadFailure)

export type EvidenceState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; map: EvidenceMap }
  | { status: 'omitted'; omission: EvidenceOmission }
  | { status: 'unsaved' }
  | ({ status: 'failed' } & LoadFailure)

/** Backend-Code fuer „fuer diese Simulation laeuft bereits ein Report“ (HTTP 409). */
export const REPORT_GENERATE_IN_PROGRESS_CODE = 'report_generate_in_progress'

const RUNNING_REPORT_STATUSES = new Set(['pending', 'planning', 'generating'])
const TERMINAL_WITH_EVIDENCE_STATUSES = new Set(['completed', 'incomplete'])
const TERMINAL_REPORT_STATUSES = new Set(['completed', 'incomplete', 'failed'])
const ACTIVE_REGISTRY_RUN_STATUSES = new Set(['pending', 'processing'])

/** Ist der Bericht in einer aktiven Erzeugungsphase (`pending`, `planning`, `generating`)? */
export function isReportRunningStatus(status: string | null | undefined): boolean {
  return typeof status === 'string' && RUNNING_REPORT_STATUSES.has(status)
}

/** Hat der Bericht einen Endzustand erreicht, fuer den Belege/Artefakte geladen werden (`completed`, `incomplete`)? */
export function isReportTerminalWithEvidence(status: string | null | undefined): boolean {
  return typeof status === 'string' && TERMINAL_WITH_EVIDENCE_STATUSES.has(status)
}

/** Ist der Bericht in einem beliebigen Endzustand (`completed`, `incomplete`, `failed`)? */
export function isReportTerminalStatus(status: string | null | undefined): boolean {
  return typeof status === 'string' && TERMINAL_REPORT_STATUSES.has(status)
}

/**
 * Beweist die Status-Antwort einen aktiven Run-Registry-Job fuer `reportId`?
 * `run_id` stammt ausschliesslich aus `_status_from_run_registry`; die Quittung
 * fuer unbekannte Kennungen (`_acknowledge_polling`) traegt kein `run_id`.
 */
export function isActiveRegistryRunForReport(statusEnvelope: unknown, reportId: string): boolean {
  if (!statusEnvelope || typeof statusEnvelope !== 'object') return false
  const env = statusEnvelope as {
    success?: boolean
    data?: { report_id?: unknown; run_id?: unknown; status?: unknown }
  }
  const data = env.success ? env.data : null
  return (
    !!data &&
    data.report_id === reportId &&
    typeof data.run_id === 'string' &&
    data.run_id !== '' &&
    typeof data.status === 'string' &&
    ACTIVE_REGISTRY_RUN_STATUSES.has(data.status)
  )
}

/**
 * Erkennt die 409-Antwort eines zweiten Starts (`report_generate_in_progress`),
 * sowohl als geworfener `ApiError` als auch als Envelope-Objekt.
 */
export function isGenerateInProgressError(value: unknown): boolean {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { code?: unknown }).code === REPORT_GENERATE_IN_PROGRESS_CODE
  )
}

/**
 * Extrahiert aus einer `getReportStatus`-Antwort die `report_id` eines noch
 * laufenden Berichts, an den sich die Ansicht nach 409 anhängen kann.
 */
export function extractAttachableRunningReportId(statusEnvelope: unknown): string | null {
  if (!statusEnvelope || typeof statusEnvelope !== 'object') return null
  const env = statusEnvelope as {
    success?: boolean
    data?: { report_id?: unknown; status?: unknown }
  }
  if (!env.success || !env.data) return null
  const runningId = typeof env.data.report_id === 'string' && env.data.report_id ? env.data.report_id : null
  const runningStatus = typeof env.data.status === 'string' ? env.data.status : ''
  if (!runningId || isReportTerminalStatus(runningStatus)) return null
  return runningId
}

/** Lesbare Fehlerbeschreibung aus einem beliebigen Fehlerwert. */
export function describeReportError(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  return String(err)
}

/** Klassifiziert einen geworfenen Ladefehler in `notFound`, `contract` oder `transport`. */
export function classifyReportLoadError(
  err: unknown,
  fallbackKind: LoadFailure['kind'] = 'transport',
): LoadFailure {
  if (err instanceof ApiError) {
    if (err.status === 404) return { kind: 'notFound', reason: err.message }
    if (err.code === 'schema_mismatch') return { kind: 'contract', reason: err.message }
  }
  return { kind: fallbackKind, reason: describeReportError(err) }
}

/** Ist ein Fehler oder Fehler-Envelope ein erwartbarer 404 („nicht gespeichert“)? */
export function isUnsavedNotFoundError(errOrEnvelope: unknown): boolean {
  if (errOrEnvelope instanceof ApiError && errOrEnvelope.status === 404) return true
  if (errOrEnvelope && typeof errOrEnvelope === 'object') {
    return (errOrEnvelope as { code?: unknown }).code === 'not_found'
  }
  return false
}

/** Formatiert Zod-Issues oder sonstige Schemafehler fuer die Anzeige. */
export function formatSchemaIssues(error: unknown): string[] {
  if (
    error &&
    typeof error === 'object' &&
    Array.isArray((error as { issues?: unknown }).issues)
  ) {
    return (error as { issues: Array<{ path: unknown[]; message: string }> }).issues.map(
      (i) => `${i.path.length ? i.path.join('.') : '<root>'}: ${i.message}`,
    )
  }
  return [describeReportError(error)]
}

/** Klassifiziert die Antwort von `GET /api/report/<id>` in einen `ReportState`. */
export function classifyReportEnvelope(id: string, res: unknown): ReportState {
  const env = res as { success?: boolean; data?: unknown; error?: string; code?: string } | null
  if (!env?.success) {
    return {
      status: 'failed',
      kind: isUnsavedNotFoundError(env) ? 'notFound' : 'transport',
      reason: env?.error || 'getReport',
    }
  }
  const parsed = ReportSchema.safeParse(env.data)
  if (!parsed.success) {
    return {
      status: 'failed',
      kind: 'contract',
      reason: `Vertragsbruch GET /api/report/${id}: ${parsed.error.message}`,
    }
  }
  return { status: 'ok', report: parsed.data }
}

/** Klassifiziert die Antwort von `GET /api/report/<id>/evidence` in einen `EvidenceState`. */
export function classifyEvidenceEnvelope(res: EvidenceEnvelope): EvidenceState {
  if (res.success !== true) {
    const err = res as { error?: string; code?: string }
    if (isUnsavedNotFoundError(err)) return { status: 'unsaved' }
    return { status: 'failed', kind: 'transport', reason: err.error || 'getReportEvidence' }
  }
  if ('evidence_omitted' in res) return { status: 'omitted', omission: res.evidence_omitted }
  return { status: 'ok', map: res.data }
}

/** Klassifiziert einen geworfenen Fehler von `getReportEvidence` in einen `EvidenceState`. */
export function classifyEvidenceError(err: unknown): EvidenceState {
  if (isUnsavedNotFoundError(err)) return { status: 'unsaved' }
  return { status: 'failed', ...classifyReportLoadError(err) }
}
