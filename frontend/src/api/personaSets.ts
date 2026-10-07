/**
 * Personasätze (#1807, Etappe 7): `/api/persona-sets`. Jede Antwort läuft durch
 * ein Zod-Schema (`contracts/personaSetContract`), jede Anfrage wird vor dem
 * Senden gegen die Anfrageform geprüft.
 *
 * Fehlerbild des Backends (`backend/app/api/persona_sets.py`):
 * - `409 persona_set_locked`: der Satz ist gesperrt (ein Lauf entstand daraus);
 *   nur Name/Beschreibung sind änderbar, sonst bleibt Duplizieren.
 *   -> `PersonaSetLockedError`.
 * - `409 conflict`: `username` kommt im Satz schon vor -> `PersonaSetConflictError`.
 * - `502 llm_unavailable`: der KI-Entwurf ist gescheitert. Der Auftrag war
 *   gueltig, der Anbieter nicht — die Oberflaeche unterscheidet daran
 *   „Brief pruefen" von „Anbieter nicht erreichbar" und bleibt beim
 *   `ApiError` des Response-Interceptors (`api/index.ts`).
 * - `404 not_found`, `400 validation_failed` und alles andere bleiben der
 *   `ApiError` des Response-Interceptors (`api/index.ts`).
 */
import service from './index'
import { ApiError } from './envelope'
import { readEnvelope } from '@/composables/run/simulation/simulationEnvelope'
import {
  PersonaDraftRequestSchema,
  PersonaDraftResponseSchema,
  PersonaSetCreateSchema,
  PersonaSetDeleteResponseSchema,
  PersonaSetDuplicateSchema,
  PersonaSetEntriesDeleteResponseSchema,
  PersonaSetEntriesDeleteSchema,
  PersonaSetEntryCreateSchema,
  PersonaSetEntrySchema,
  PersonaSetEntryUpdateSchema,
  PersonaSetListResponseSchema,
  PersonaSetQualityReportSchema,
  PersonaSetRecordSchema,
  PersonaSetUpdateSchema,
  type PersonaDraftRequest,
  type PersonaDraftResponse,
  type PersonaSetCreate,
  type PersonaSetDeleteResponse,
  type PersonaSetDuplicate,
  type PersonaSetEntriesDeleteResponse,
  type PersonaSetEntry,
  type PersonaSetEntryCreate,
  type PersonaSetEntryUpdate,
  type PersonaSetListResponse,
  type PersonaSetQualityReport,
  type PersonaSetRecord,
  type PersonaSetUpdate,
} from '@/contracts/personaSetContract'

export const PERSONA_SET_LOCKED_CODE = 'persona_set_locked'
export const PERSONA_SET_CONFLICT_CODE = 'conflict'

/** 409 `persona_set_locked`: Satz gesperrt, Personas nicht änderbar. */
export class PersonaSetLockedError extends Error {
  readonly code = PERSONA_SET_LOCKED_CODE
  readonly status = 409
  constructor(message: string) {
    super(message)
    this.name = 'PersonaSetLockedError'
    Object.setPrototypeOf(this, PersonaSetLockedError.prototype)
  }
}

/** 409 `conflict`: z. B. doppelter `username` im Satz. */
export class PersonaSetConflictError extends Error {
  readonly code = PERSONA_SET_CONFLICT_CODE
  readonly status = 409
  constructor(message: string) {
    super(message)
    this.name = 'PersonaSetConflictError'
    Object.setPrototypeOf(this, PersonaSetConflictError.prototype)
  }
}

export function isPersonaSetLockedError(err: unknown): err is PersonaSetLockedError {
  return err instanceof PersonaSetLockedError
}

export function isPersonaSetConflictError(err: unknown): err is PersonaSetConflictError {
  return err instanceof PersonaSetConflictError
}

/** Ordnet einen `ApiError` den typisierten 409-Fehlern zu; alles andere unverändert. */
function mapError(err: unknown): unknown {
  if (err instanceof ApiError && err.status === 409) {
    if (err.code === PERSONA_SET_LOCKED_CODE) return new PersonaSetLockedError(err.message)
    if (err.code === PERSONA_SET_CONFLICT_CODE) return new PersonaSetConflictError(err.message)
  }
  return err
}

async function send(call: () => Promise<unknown>): Promise<unknown> {
  try {
    return await call()
  } catch (err) {
    throw mapError(err)
  }
}

function base(setId: string): string {
  return `/api/persona-sets/${encodeURIComponent(setId)}`
}

export async function listPersonaSets(): Promise<PersonaSetListResponse> {
  const raw = await send(() => service.get('/api/persona-sets'))
  return readEnvelope(raw, PersonaSetListResponseSchema, 'persona-sets')
}

export async function getPersonaSet(setId: string): Promise<PersonaSetRecord> {
  const raw = await send(() => service.get(base(setId)))
  return readEnvelope(raw, PersonaSetRecordSchema, 'persona-sets/get')
}

export async function createPersonaSet(body: PersonaSetCreate): Promise<PersonaSetRecord> {
  const payload = PersonaSetCreateSchema.parse(body)
  const raw = await send(() => service.post('/api/persona-sets', payload))
  return readEnvelope(raw, PersonaSetRecordSchema, 'persona-sets/create')
}

export async function updatePersonaSet(setId: string, body: PersonaSetUpdate): Promise<PersonaSetRecord> {
  const payload = PersonaSetUpdateSchema.parse(body)
  const raw = await send(() => service.patch(base(setId), payload))
  return readEnvelope(raw, PersonaSetRecordSchema, 'persona-sets/update')
}

export async function deletePersonaSet(setId: string): Promise<PersonaSetDeleteResponse> {
  const raw = await send(() => service.delete(base(setId)))
  return readEnvelope(raw, PersonaSetDeleteResponseSchema, 'persona-sets/delete')
}

export async function duplicatePersonaSet(setId: string, body: PersonaSetDuplicate): Promise<PersonaSetRecord> {
  const payload = PersonaSetDuplicateSchema.parse(body)
  const raw = await send(() => service.post(`${base(setId)}/duplicate`, payload))
  return readEnvelope(raw, PersonaSetRecordSchema, 'persona-sets/duplicate')
}

export async function getPersonaSetQuality(setId: string): Promise<PersonaSetQualityReport> {
  const raw = await send(() => service.get(`${base(setId)}/quality`))
  return readEnvelope(raw, PersonaSetQualityReportSchema, 'persona-sets/quality')
}

export async function addPersonaSetEntry(setId: string, body: PersonaSetEntryCreate): Promise<PersonaSetEntry> {
  const payload = PersonaSetEntryCreateSchema.parse(body)
  const raw = await send(() => service.post(`${base(setId)}/entries`, payload))
  return readEnvelope(raw, PersonaSetEntrySchema, 'persona-sets/entries/add')
}

export async function updatePersonaSetEntry(
  setId: string,
  entryId: string,
  body: PersonaSetEntryUpdate,
): Promise<PersonaSetEntry> {
  const payload = PersonaSetEntryUpdateSchema.parse(body)
  const raw = await send(() => service.patch(`${base(setId)}/entries/${encodeURIComponent(entryId)}`, payload))
  return readEnvelope(raw, PersonaSetEntrySchema, 'persona-sets/entries/update')
}

export async function deletePersonaSetEntry(
  setId: string,
  entryId: string,
): Promise<PersonaSetEntriesDeleteResponse> {
  const raw = await send(() => service.delete(`${base(setId)}/entries/${encodeURIComponent(entryId)}`))
  return readEnvelope(raw, PersonaSetEntriesDeleteResponseSchema, 'persona-sets/entries/delete')
}

/** Mehrfachlöschen, alles oder nichts: eine unbekannte Kennung ergibt 404 ohne Änderung. */
export async function deletePersonaSetEntries(
  setId: string,
  entryIds: readonly string[],
): Promise<PersonaSetEntriesDeleteResponse> {
  const payload = PersonaSetEntriesDeleteSchema.parse({ entry_ids: [...entryIds] })
  const raw = await send(() => service.post(`${base(setId)}/entries/delete`, payload))
  return readEnvelope(raw, PersonaSetEntriesDeleteResponseSchema, 'persona-sets/entries/delete-many')
}

/**
 * KI-Entwurf einer Persona. Der Endpunkt legt den Eintrag direkt an — der
 * Aufrufer entscheidet also **vorher**, ob er einen Entwurf will, und kann ihn
 * danach wie jeden anderen Eintrag bearbeiten oder loeschen.
 *
 * Ein gesperrter Satz lehnt den Aufruf mit `409 persona_set_locked` ab, ohne
 * das Modell zu rufen: der Dienst prueft die Sperre vor dem Aufruf.
 */
export async function draftPersonaSetEntry(
  setId: string,
  body: PersonaDraftRequest,
): Promise<PersonaDraftResponse> {
  const parsed = PersonaDraftRequestSchema.parse(body)
  const raw = await send(() =>
    service.post(`${base(setId)}/draft`, {
      brief: parsed.brief,
      language: parsed.language ?? 'de',
    }),
  )
  return readEnvelope(raw, PersonaDraftResponseSchema, `persona-draft ${setId}`)
}
