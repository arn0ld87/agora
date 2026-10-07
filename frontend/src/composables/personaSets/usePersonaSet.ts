/**
 * Ein Personasatz (#1807, Etappe 7): laden, Einträge anlegen/ändern/löschen,
 * Mehrfachlöschen, Qualität, Name/Beschreibung.
 *
 * Zustände bleiben sichtbar getrennt: `error` (Laden), `actionError` (letzte
 * Aktion), `conflictError` (409 `conflict`, z. B. doppelter `username`) und
 * `isLocked`. Wird eine Änderung mit 409 `persona_set_locked` abgelehnt, ist der
 * lokale Stand veraltet: `isLocked` wird wahr, der Satz wird neu geladen.
 */
import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import {
  addPersonaSetEntry,
  deletePersonaSetEntries,
  deletePersonaSetEntry,
  getPersonaSet,
  getPersonaSetQuality,
  isPersonaSetConflictError,
  isPersonaSetLockedError,
  updatePersonaSet,
  updatePersonaSetEntry,
} from '@/api/personaSets'
import { ApiError } from '@/api/envelope'
import { describeError } from '@/composables/run/simulation/simulationEnvelope'
import type {
  PersonaSetEntry,
  PersonaSetEntryCreate,
  PersonaSetEntryUpdate,
  PersonaSetQualityReport,
  PersonaSetRecord,
  PersonaSetUpdate,
} from '@/contracts/personaSetContract'

export function usePersonaSet(setId: MaybeRefOrGetter<string>) {
  const record = ref<PersonaSetRecord | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** Ladefehler war 404: der Satz existiert nicht (mehr). */
  const notFound = ref(false)
  const actionError = ref<string | null>(null)
  const conflictError = ref(false)
  const lockedByServer = ref(false)
  const busy = ref(false)

  const quality = ref<PersonaSetQualityReport | null>(null)
  const qualityLoading = ref(false)
  const qualityError = ref<string | null>(null)

  const isLocked = computed(() => lockedByServer.value || (record.value?.locked_at ?? null) !== null)
  const entries = computed<PersonaSetEntry[]>(() => record.value?.entries ?? [])

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    notFound.value = false
    try {
      record.value = await getPersonaSet(toValue(setId))
      lockedByServer.value = false
    } catch (err) {
      record.value = null
      notFound.value = err instanceof ApiError && err.status === 404
      error.value = describeError(err)
    } finally {
      loading.value = false
    }
  }

  async function loadQuality(): Promise<void> {
    qualityLoading.value = true
    qualityError.value = null
    try {
      quality.value = await getPersonaSetQuality(toValue(setId))
    } catch (err) {
      quality.value = null
      qualityError.value = describeError(err)
    } finally {
      qualityLoading.value = false
    }
  }

  async function act<T>(run: () => Promise<T>): Promise<T | null> {
    busy.value = true
    actionError.value = null
    conflictError.value = false
    try {
      return await run()
    } catch (err) {
      actionError.value = describeError(err)
      conflictError.value = isPersonaSetConflictError(err)
      if (isPersonaSetLockedError(err)) {
        lockedByServer.value = true
        // Lokaler Stand ist veraltet; neu laden, `actionError` bleibt stehen.
        const message = actionError.value
        await load()
        lockedByServer.value = true
        actionError.value = message
      }
      return null
    } finally {
      busy.value = false
    }
  }

  /** Legt einen Eintrag an; gibt ihn zurück oder `null` bei Fehler. */
  async function addEntry(body: PersonaSetEntryCreate): Promise<PersonaSetEntry | null> {
    const entry = await act(() => addPersonaSetEntry(toValue(setId), body))
    if (entry && record.value) {
      record.value = { ...record.value, entries: [...record.value.entries, entry] }
    }
    return entry
  }

  async function updateEntry(entryId: string, body: PersonaSetEntryUpdate): Promise<PersonaSetEntry | null> {
    const entry = await act(() => updatePersonaSetEntry(toValue(setId), entryId, body))
    if (entry && record.value) {
      record.value = {
        ...record.value,
        entries: record.value.entries.map((e) => (e.entry_id === entryId ? entry : e)),
      }
    }
    return entry
  }

  async function deleteEntry(entryId: string): Promise<boolean> {
    const res = await act(() => deletePersonaSetEntry(toValue(setId), entryId))
    if (res && record.value) removeLocal(res.removed_entry_ids)
    return res !== null
  }

  /** Alles oder nichts: bei Fehler bleibt die Liste unverändert. */
  async function deleteEntries(entryIds: readonly string[]): Promise<boolean> {
    const res = await act(() => deletePersonaSetEntries(toValue(setId), entryIds))
    if (res && record.value) removeLocal(res.removed_entry_ids)
    return res !== null
  }

  function removeLocal(ids: readonly string[]): void {
    if (!record.value) return
    const gone = new Set(ids)
    record.value = { ...record.value, entries: record.value.entries.filter((e) => !gone.has(e.entry_id)) }
  }

  /** Name/Beschreibung ändern; bleibt auch bei gesperrtem Satz erlaubt. */
  async function updateMeta(body: PersonaSetUpdate): Promise<boolean> {
    const updated = await act(() => updatePersonaSet(toValue(setId), body))
    if (updated) record.value = updated
    return updated !== null
  }

  watch(
    () => toValue(setId),
    () => {
      quality.value = null
      qualityError.value = null
      actionError.value = null
      conflictError.value = false
    },
  )

  return {
    record,
    entries,
    loading,
    error,
    notFound,
    actionError,
    conflictError,
    busy,
    isLocked,
    quality,
    qualityLoading,
    qualityError,
    load,
    loadQuality,
    addEntry,
    updateEntry,
    deleteEntry,
    deleteEntries,
    updateMeta,
  }
}
