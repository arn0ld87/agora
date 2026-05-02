// Issue #133 — Settings-Store.
//
// Reactive Container für den Schema-Cache (1× pro Session geladen,
// danach stabil) und den aktuellen Sektions-Snapshot, plus die dirty-
// Tracking-Logik der Settings-View.
//
// Bewusst kein Pinia/Vuex: das Repo nutzt einfache reactive-Singletons
// (siehe ``store/pendingUpload.js``) und das passt hier ebenfalls — die
// Daten leben nur in der Settings-View.

import { reactive } from 'vue'
import {
  fetchSettings,
  fetchSettingsSchema,
  putSecrets,
  putSettings,
} from '../api/settings'

const state = reactive({
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


function _resetDraftFromFields() {
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


export async function loadSettings() {
  state.loading = true
  state.loadError = null
  try {
    const [schemaRes, valuesRes] = await Promise.all([
      fetchSettingsSchema(),
      fetchSettings(),
    ])
    const schemaBody = schemaRes.data
    const valuesBody = valuesRes.data
    state.sections = valuesBody.data.sections
    state.schema = schemaBody.data.fields
    state.fields = valuesBody.data.fields
    _resetDraftFromFields()
  } catch (err) {
    state.loadError = err?.message || 'Fehler beim Laden der Einstellungen.'
    throw err
  } finally {
    state.loading = false
  }
}


export function isDirty(key) {
  // Secrets gelten als dirty, sobald der Draft nicht-leer ist —
  // egal ob der serverseitige Wert schon gesetzt ist (Klartext kennen
  // wir im Frontend ohnehin nicht).
  const spec = _findSpec(key)
  if (spec?.secret) {
    return (state.draft[key] || '') !== ''
  }
  const meta = _findFieldMeta(key)
  if (!meta) return false
  return state.draft[key] !== meta.value
}


export function dirtyKeys() {
  const keys = []
  for (const section of state.sections) {
    for (const item of state.fields[section] || []) {
      if (isDirty(item.key)) keys.push(item.key)
    }
  }
  return keys
}


export function dirtySectionFlags() {
  // Helper: pro Sektion ein bool, ob mindestens ein Field dirty ist.
  // Wird vom Tab-Renderer für Indikator-Punkte genutzt.
  const out = {}
  for (const section of state.sections) {
    out[section] = (state.fields[section] || []).some((item) => isDirty(item.key))
  }
  return out
}


function _findSpec(key) {
  return state.schema.find((s) => s.key === key) || null
}


function _findFieldMeta(key) {
  for (const section of state.sections) {
    for (const item of state.fields[section] || []) {
      if (item.key === key) return item
    }
  }
  return null
}


function _splitDirtyByKind() {
  const nonSecrets = {}
  const secrets = {}
  for (const key of dirtyKeys()) {
    const spec = _findSpec(key)
    if (spec?.secret) {
      secrets[key] = state.draft[key]
    } else {
      nonSecrets[key] = state.draft[key]
    }
  }
  return { nonSecrets, secrets }
}


export async function saveSettings({ confirmSecrets = false } = {}) {
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
    const err = new Error('confirm_secrets_required')
    err.code = 'confirm_secrets_required'
    throw err
  }

  state.saving = true
  try {
    let lastResponse = null
    if (hasNonSecrets) {
      lastResponse = await putSettings(nonSecrets)
    }
    if (hasSecrets) {
      lastResponse = await putSecrets(secrets)
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
    state.saveError = err?.message || 'Fehler beim Speichern.'
    // Validation-Fehler liefert das Backend als Liste — die View
    // rendert sie pro Field als Inline-Hint.
    if (err?.originalResponse?.errors) {
      state.validationErrors = err.originalResponse.errors
    }
    throw err
  } finally {
    state.saving = false
  }
}


export function discardChanges() {
  _resetDraftFromFields()
  state.validationErrors = []
  state.saveError = null
}


export function fieldErrors(key) {
  return state.validationErrors.filter((e) => e.key === key)
}


export default state
