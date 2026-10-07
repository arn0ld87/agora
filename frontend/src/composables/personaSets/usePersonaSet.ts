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
  draftPersonaSetEntry,
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
  PersonaDraftExamplePost,
  PersonaDraftResponse,
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

  /** Der zuletzt erzeugte Beispielbeitrag, getrennt vom Eintrag.
   *
   *  Er gehoert nicht zum Satz (der Feed der Simulation erzeugt eigene
   *  Beitraege), wird aber angezeigt, damit die Stimme der Persona
   *  beurteilbar ist, bevor der Eintrag bleibt. Nach dem Bearbeiten oder
   *  Loeschen des Eintrags faellt er weg — sonst gehoerte der Beitrag zu
   *  einer Persona, die es nicht mehr gibt.
   */
  const draftExample = ref<PersonaDraftExamplePost | null>(null)
  /** Der Eintrag, den der letzte Entwurf angelegt hat (fuer den Fokus). */
  const draftEntryId = ref<string | null>(null)
  const drafting = ref(false)
  /** 502 `llm_unavailable`: der Anbieter war schuld, nicht der Brief. */
  const draftProviderError = ref(false)

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
    if (entry && draftEntryId.value === entryId) clearDraftExample()
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
    if (res && draftEntryId.value === entryId) clearDraftExample()
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

  /**
   * KI-Entwurf: legt einen Eintrag mit `origin="ai_draft"` an.
   *
   * Zwei Zustaende statt einem: `drafting` (laeuft) und `draftProviderError`
   * (502). Die Oberflaeche muss dazwischen unterscheiden koennen — ein nicht
   * erreichbarer Anbieter und ein zu kurzer Brief brauchen verschiedene
   * Handlungen, und beide kommen als "Fehler" aus demselben Aufruf.
   *
   * Gibt die Antwort zurueck oder `null`. Der Eintrag wird lokal eingefuegt,
   * damit die Liste ohne zweiten Abruf den neuen Eintrag zeigt; die Vorschau
   * mit dem Beispielbeitrag bleibt bis zum Bearbeiten oder Loeschen stehen.
   */
  async function draft(brief: string, language = 'de'): Promise<PersonaDraftResponse | null> {
    drafting.value = true
    actionError.value = null
    draftProviderError.value = false
    try {
      const response = await draftPersonaSetEntry(toValue(setId), { brief, language })
      const entry: PersonaSetEntry = {
        entry_id: '',
        origin: 'ai_draft',
        profile: response.profile,
        created_at: '',
        updated_at: '',
        source_entity_uuid: null,
      }
      // Der Server vergibt entry_id und Zeitstempel; statt sie zu raten,
      // wird der Satz einmal neu geladen. Ein erfundener Eintrag ohne Kennung
      // waere beim naechsten Bearbeiten nicht adressierbar.
      await load()
      const created = entries.value[entries.value.length - 1]
      draftExample.value = response.example_post
      draftEntryId.value = created?.entry_id ?? null
      return { ...response, profile: (created ?? entry).profile }
    } catch (err) {
      actionError.value = describeError(err)
      draftProviderError.value = err instanceof ApiError && err.status === 502
      if (isPersonaSetLockedError(err)) {
        // Ein gesperrter Satz lehnt den Entwurf ab, ohne das Modell zu rufen.
        lockedByServer.value = true
        const message = actionError.value
        await load()
        lockedByServer.value = true
        actionError.value = message
      }
      return null
    } finally {
      drafting.value = false
    }
  }

  /** Verwirft die Vorschau des letzten Entwurfs. */
  function clearDraftExample(): void {
    draftExample.value = null
    draftEntryId.value = null
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
      clearDraftExample()
      draftProviderError.value = false
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
    draftExample,
    draftEntryId,
    drafting,
    draftProviderError,
    load,
    loadQuality,
    draft,
    clearDraftExample,
    addEntry,
    updateEntry,
    deleteEntry,
    deleteEntries,
    updateMeta,
  }
}
