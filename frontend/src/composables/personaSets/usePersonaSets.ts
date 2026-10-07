/**
 * Liste der Personasätze (#1807, Etappe 7): laden, anlegen, duplizieren, löschen.
 * Lade- und Aktionsfehler bleiben getrennt sichtbar; nichts wird geschluckt.
 * Ein gesperrter Satz (409 `persona_set_locked`) beim Löschen o. Ä. steht als
 * eigener Zustand `lockedError` bereit.
 */
import { computed, ref } from 'vue'
import {
  createPersonaSet,
  deletePersonaSet,
  duplicatePersonaSet,
  isPersonaSetLockedError,
  listPersonaSets,
} from '@/api/personaSets'
import { describeError } from '@/composables/run/simulation/simulationEnvelope'
import type {
  PersonaSetCreate,
  PersonaSetRecord,
  PersonaSetSummary,
} from '@/contracts/personaSetContract'

export function usePersonaSets() {
  const sets = ref<PersonaSetSummary[]>([])
  const loading = ref(false)
  /** Fehler beim Laden der Liste. */
  const error = ref<string | null>(null)
  /** Fehler der letzten Aktion (anlegen, duplizieren, löschen). */
  const actionError = ref<string | null>(null)
  /** Die letzte Aktion scheiterte an einem gesperrten Satz. */
  const lockedError = ref(false)
  const busy = ref(false)
  const loaded = ref(false)

  const isEmpty = computed(() => loaded.value && !loading.value && !error.value && sets.value.length === 0)

  async function reload(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      sets.value = (await listPersonaSets()).sets
      loaded.value = true
    } catch (err) {
      error.value = describeError(err)
    } finally {
      loading.value = false
    }
  }

  async function act<T>(run: () => Promise<T>): Promise<T | null> {
    busy.value = true
    actionError.value = null
    lockedError.value = false
    try {
      return await run()
    } catch (err) {
      lockedError.value = isPersonaSetLockedError(err)
      actionError.value = describeError(err)
      return null
    } finally {
      busy.value = false
    }
  }

  async function create(body: PersonaSetCreate): Promise<PersonaSetRecord | null> {
    const record = await act(() => createPersonaSet(body))
    if (record) await reload()
    return record
  }

  async function duplicate(setId: string, name: string): Promise<PersonaSetRecord | null> {
    const record = await act(() => duplicatePersonaSet(setId, { name }))
    if (record) await reload()
    return record
  }

  /** `true`, wenn der Satz gelöscht wurde. */
  async function remove(setId: string): Promise<boolean> {
    const res = await act(() => deletePersonaSet(setId))
    if (res) await reload()
    return res !== null
  }

  return {
    sets,
    loading,
    loaded,
    error,
    actionError,
    lockedError,
    busy,
    isEmpty,
    reload,
    create,
    duplicate,
    remove,
  }
}
