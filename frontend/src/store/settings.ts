// Issue #133 — Settings-Store.
//
// Reactive Container für den Schema-Cache (1× pro Session geladen,
// danach stabil) und den aktuellen Sektions-Snapshot, plus die dirty-
// Tracking-Logik der Settings-View.
//
// Bewusst kein Pinia/Vuex: das Repo nutzt einfache reactive-Singletons
// (siehe ``store/pendingUpload.ts``) und das passt hier ebenfalls — die
// Daten leben nur in der Settings-View.

import { reactive } from 'vue'
import {
  fetchSettings,
  fetchSettingsSchema,
  putSecrets,
  putSettings,
} from '../api/settings'
import type { SecretsPayload } from '../api/settings'

// FieldSpec beschreibt die Schema-Beschreibung eines Feldes (kein Laufzeit-Wert).
export interface FieldSpec {
  key: string
  section?: string
  type?: string
  secret: boolean
  reload_required?: boolean
  default?: unknown
}

// FieldMeta beschreibt einen einzelnen Einstellungs-Wert wie er vom
// Backend in der /api/settings-Antwort geliefert wird.
export interface FieldMeta {
  key: string
  section: string
  type: string
  secret: boolean
  reload_required: boolean
  value: unknown
  default: unknown
  source?: string
  is_set?: boolean
}

// ValidationError ist ein einzelner Validierungsfehler vom Backend.
export interface ValidationError {
  key: string
  code: string
  message: string
}

interface SettingsState {
  loading: boolean
  saving: boolean
  loadError: string | null
  saveError: string | null
  sections: string[]
  schema: FieldSpec[]
  fields: Record<string, FieldMeta[]>
  draft: Record<string, unknown>
  drafts_secret_filled: Record<string, boolean>
  validationErrors: ValidationError[]
}

// Erweiterter Error-Typ für Backend-Validierungsfehler, die zusätzlich
// `code` und `originalResponse` tragen.
interface SettingsApiError extends Error {
  code?: string
  originalResponse?: {
    errors?: ValidationError[]
  }
}

// Die API-Funktionen in api/settings.ts deklarieren breite Record-Returns.
// Die tatsächliche Envelope-Shape, auf die der Store zugreift, ist:
//   apiResponse.data  →  { success: true, data: { ... } }
//   apiResponse.data.data.sections / .fields
// reason: Vollständige Zod-Validierung dieser Responses ist Layer-4-Scope (#76).
// reason: Test-Mocks liefern axios-ähnliche Struktur { data: { data: { ... } } };
//   in production gibt der Interceptor den Envelope-Body direkt zurück.
//   Die .data.data-Doppeltiefe spiegelt die bestehende, funktionierende Logik.
type SettingsApiResponse = {
  data: {
    data: {
      sections: string[]
      fields: Record<string, FieldMeta[]>
    }
  }
}
type SchemaApiResponse = {
  data: {
    data: {
      fields: FieldSpec[]
    }
  }
}

const state = reactive<SettingsState>({
  loading: false,
  saving: false,
  loadError: null,
  saveError: null,
  // Liste der Sektions-IDs in UI-Reihenfolge (vom Backend geliefert).
  sections: [],
  // Reine Schema-Beschreibung (Field-Specs ohne aktuelle Werte).
  schema: [],
  // Aktueller Wert + Source pro Field, gruppiert nach Sektion.
  fields: {},
  // Form-State pro Field-Key (entspricht dem im Input gerenderten
  // Wert). Wird beim Load aus ``fields`` initialisiert; dirty-
  // Tracking vergleicht gegen ``fields[*].value``.
  draft: {},
  // Fields, deren `is_set: true` ist — wichtig für Secret-UI:
  // „aktuell gesetzt" vs. „leer" rendert anders, und ein leeres
  // Secret-Input darf nicht versehentlich auf "" zurückspringen.
  drafts_secret_filled: {},
  // Letzter Validation-Error vom Backend (Liste von {key,code,message}).
  validationErrors: [],
})


function _resetDraftFromFields(): void {
  state.draft = {}
  for (const section of state.sections) {
    for (const item of state.fields[section] || []) {
      // Secret-Felder kriegen einen leeren Draft — das Input ist
      // ein Passwort-Field, das beim Tippen vom leeren String aus
      // startet. Der "is_set"-Status zeigt separat an, dass schon
      // ein Wert existiert.
      if (item.secret) {
        state.draft[item.key] = ''
      } else {
        state.draft[item.key] = item.value
      }
    }
  }
}


export async function loadSettings(): Promise<void> {
  state.loading = true
  state.loadError = null
  try {
    const [schemaRes, valuesRes] = await Promise.all([
      fetchSettingsSchema(),
      fetchSettings(),
    ])
    // reason: api/settings.ts deklariert breite Record-Returns; tatsächliche
    // Envelope-Shape ist SchemaApiResponse / SettingsApiResponse.
    // Zod-Strict-Validierung ist Layer-4-Scope (#76).
    const schemaBody = schemaRes as unknown as SchemaApiResponse
    const valuesBody = valuesRes as unknown as SettingsApiResponse
    state.sections = valuesBody.data.data.sections
    state.schema = schemaBody.data.data.fields
    state.fields = valuesBody.data.data.fields
    _resetDraftFromFields()
  } catch (err) {
    const e = err as Error
    state.loadError = e?.message || 'Fehler beim Laden der Einstellungen.'
    throw err
  } finally {
    state.loading = false
  }
}


export function isDirty(key: string): boolean {
  // Secrets gelten als dirty, sobald der Draft nicht-leer ist —
  // egal ob der serverseitige Wert schon gesetzt ist (Klartext kennen
  // wir im Frontend ohnehin nicht).
  const spec = _findSpec(key)
  if (spec?.secret) {
    return ((state.draft[key] as string) || '') !== ''
  }
  const meta = _findFieldMeta(key)
  if (!meta) return false
  return state.draft[key] !== meta.value
}


export function dirtyKeys(): string[] {
  const keys: string[] = []
  for (const section of state.sections) {
    for (const item of state.fields[section] || []) {
      if (isDirty(item.key)) keys.push(item.key)
    }
  }
  return keys
}


export function dirtySectionFlags(): Record<string, boolean> {
  // Helper: pro Sektion ein bool, ob mindestens ein Field dirty ist.
  // Wird vom Tab-Renderer für Indikator-Punkte genutzt.
  const out: Record<string, boolean> = {}
  for (const section of state.sections) {
    out[section] = (state.fields[section] || []).some((item) => isDirty(item.key))
  }
  return out
}


function _findSpec(key: string): FieldSpec | null {
  return state.schema.find((s) => s.key === key) || null
}


function _findFieldMeta(key: string): FieldMeta | null {
  for (const section of state.sections) {
    for (const item of state.fields[section] || []) {
      if (item.key === key) return item
    }
  }
  return null
}


function _splitDirtyByKind(): { nonSecrets: Record<string, unknown>; secrets: SecretsPayload } {
  const nonSecrets: Record<string, unknown> = {}
  const secrets: SecretsPayload = {}
  for (const key of dirtyKeys()) {
    const spec = _findSpec(key)
    if (spec?.secret) {
      secrets[key] = state.draft[key] as string
    } else {
      nonSecrets[key] = state.draft[key]
    }
  }
  return { nonSecrets, secrets }
}


export async function saveSettings({ confirmSecrets = false }: { confirmSecrets?: boolean } = {}): Promise<unknown> {
  // Erwartung: View ruft ``saveSettings({ confirmSecrets: true })`` erst,
  // nachdem die Operatorin den Modal-Dialog für Secrets bestätigt hat.
  // Wenn dirty-Set Secrets enthält, ohne ``confirmSecrets``, werfen wir
  // synchron — die View behandelt das als „Modal öffnen, nicht senden".
  state.saveError = null
  state.validationErrors = []
  const { nonSecrets, secrets } = _splitDirtyByKind()
  const hasSecrets = Object.keys(secrets).length > 0
  const hasNonSecrets = Object.keys(nonSecrets).length > 0

  if (hasSecrets && !confirmSecrets) {
    const err = Object.assign(new Error('confirm_secrets_required'), {
      code: 'confirm_secrets_required',
    })
    throw err
  }

  state.saving = true
  try {
    // reason: api/settings.ts Returns sind breite Records; tatsächliche
    // Envelope-Shape ist SettingsApiResponse. Zod-Strict-Validierung ist Layer-4.
    let lastResponse: SettingsApiResponse | null = null
    if (hasNonSecrets) {
      lastResponse = await putSettings(nonSecrets) as unknown as SettingsApiResponse
    }
    if (hasSecrets) {
      lastResponse = await putSecrets(secrets) as unknown as SettingsApiResponse
    }
    if (lastResponse) {
      // Beide Endpunkte liefern den frischen Sektions-Snapshot —
      // wir adoptieren ihn direkt, statt einen GET nachzuschicken.
      state.sections = lastResponse.data.data.sections
      state.fields = lastResponse.data.data.fields
      _resetDraftFromFields()
    }
    return lastResponse?.data || null
  } catch (err) {
    const e = err as SettingsApiError
    state.saveError = e?.message || 'Fehler beim Speichern.'
    // Validation-Fehler liefert das Backend als Liste — die View
    // rendert sie pro Field als Inline-Hint.
    if (e?.originalResponse?.errors) {
      state.validationErrors = e.originalResponse.errors
    }
    throw err
  } finally {
    state.saving = false
  }
}


export function discardChanges(): void {
  _resetDraftFromFields()
  state.validationErrors = []
  state.saveError = null
}


export function fieldErrors(key: string): ValidationError[] {
  return state.validationErrors.filter((e) => e.key === key)
}


export default state
