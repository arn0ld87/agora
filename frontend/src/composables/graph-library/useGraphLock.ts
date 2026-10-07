/**
 * Sperrzustand eines Graphen (#1808, Etappe 8, ADR-0022 §6).
 *
 * Gesperrt ist ein Graph, sobald eine Simulation ihn oder sein Projekt
 * verwendet. Der Zustand kommt bei jeder Abfrage frisch aus dem Backend
 * (`GET /api/graph/<graph_id>/lock`); die Bibliothek adressiert Graphen per
 * `project_id`, die Endpunkte per `graph_id`, daher nimmt das Composable die
 * `graph_id`.
 *
 * Zustaende:
 *   unknown  – noch keine Antwort (oder keine graph_id); Oberflaechen sperren
 *              das Bearbeiten vorsorglich, bis der Zustand bekannt ist
 *   editable – nicht gesperrt
 *   locked   – eine Simulation verwendet den Graphen (`usedBy`)
 *   error    – Abfrage gescheitert (sichtbar, nicht als „bearbeitbar“ gelesen)
 */
import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { getGraphLock } from '@/api/graphEdit'
import type { GraphLockUser } from '@/contracts/graphEditContract'

export type GraphLockStatus = 'unknown' | 'editable' | 'locked' | 'error'

export function useGraphLock(graphId: MaybeRefOrGetter<string | null | undefined>) {
  const status = ref<GraphLockStatus>('unknown')
  const usedBy = ref<GraphLockUser[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let seq = 0

  const locked = computed(() => status.value === 'locked')
  const editable = computed(() => status.value === 'editable')

  async function reload(): Promise<void> {
    const id = toValue(graphId)
    const mySeq = ++seq
    if (!id) {
      status.value = 'unknown'
      usedBy.value = []
      error.value = null
      loading.value = false
      return
    }
    loading.value = true
    try {
      const state = await getGraphLock(id)
      if (mySeq !== seq) return
      usedBy.value = state.used_by
      status.value = state.locked ? 'locked' : 'editable'
      error.value = null
    } catch (caught) {
      if (mySeq !== seq) return
      status.value = 'error'
      usedBy.value = []
      error.value = caught instanceof Error && caught.message ? caught.message : String(caught)
    } finally {
      if (mySeq === seq) loading.value = false
    }
  }

  /** Setzt den Zustand „gesperrt“ sichtbar, etwa nach einem 409 `graph_locked`. */
  function markLocked(users: GraphLockUser[]): void {
    seq++
    usedBy.value = users
    status.value = 'locked'
    error.value = null
    loading.value = false
  }

  watch(() => toValue(graphId), () => void reload(), { immediate: true })

  return { status, locked, editable, usedBy, loading, error, reload, markLocked }
}

export type GraphLock = ReturnType<typeof useGraphLock>
