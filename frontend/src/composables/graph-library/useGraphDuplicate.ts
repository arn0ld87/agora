/**
 * Kopierauftrag eines gesperrten Graphen (#1808, Etappe 8, Entscheid 3).
 *
 * Ein gesperrter Graph lässt sich nicht bearbeiten; der Ausweg ist eine
 * unabhängige Kopie. Der Auftrag läuft als Hintergrundjob in der RunRegistry
 * (`run_type='graph_duplicate'`), deshalb gibt es keinen Sofort-Endzustand:
 * `duplicateGraph` liefert `pending` mit den Kennungen der Kopie, und der
 * Zustand kommt über `GET /api/runs/<run_id>` nach.
 *
 * Solange der Auftrag nicht terminal ist, wird gepollt; danach nicht. Beim
 * Verlassen der Ansicht hört das Polling auf (kein Timer ohne Konsumenten).
 */
import { computed, getCurrentScope, onScopeDispose, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'
import { duplicateGraph, getGraphDuplicateRun } from '@/api/graphEdit'
import { isGraphDuplicateTerminal, type GraphDuplicateRun } from '@/contracts/graphEditContract'

/** 1,5 s: schnell genug, dass der Fortschritt lebt, langsam genug für den Stack. */
export const DUPLICATE_POLL_MS = 1500

export type GraphDuplicateErrorKind = 'build_running' | 'migration_running' | 'unavailable' | 'invalid_input' | 'other'

export interface GraphDuplicateFailure {
  kind: GraphDuplicateErrorKind
  message: string
}

export interface GraphDuplicateProgress {
  /** 0–100, solange der Auftrag läuft. */
  percent: number
  /** Meldung des Auftrags (nicht übersetzt: sie kommt vom Server). */
  message: string
}

function classify(caught: unknown): GraphDuplicateFailure {
  const name = caught instanceof Error ? caught.name : ''
  const message = caught instanceof Error && caught.message ? caught.message : String(caught)
  if (name === 'GraphBuildInProgressError') return { kind: 'build_running', message }
  if (name === 'EmbeddingMigrationRunningError') return { kind: 'migration_running', message }
  if (name === 'GraphDuplicateUnavailableError') return { kind: 'unavailable', message }
  if (name === 'GraphEditInputError') return { kind: 'invalid_input', message }
  return { kind: 'other', message }
}

export function useGraphDuplicate(
  graphId: MaybeRefOrGetter<string | null | undefined>,
  options: { pollMs?: number } = {},
) {
  const pollMs = options.pollMs ?? DUPLICATE_POLL_MS

  const job = ref<{ graphId: string; projectId: string; runId: string } | null>(null)
  const status = ref<GraphDuplicateRun['status'] | null>(null)
  const progress = ref<GraphDuplicateProgress>({ percent: 0, message: '' })
  const error = ref<GraphDuplicateFailure | null>(null)
  const busy = ref(false)

  let timer: ReturnType<typeof setTimeout> | null = null
  let seq = 0

  /** `completed` heißt: die Kopie ist lesbar. Erst dann ist „Kopie“ eine Tatsache. */
  const completed = computed(() => status.value === 'completed')
  const failed = computed(() => status.value === 'failed' || status.value === 'stopped')
  /** Zielprojekt der Kopie — die Adresse, auf die der Ausweg führt. */
  const copyProjectId = computed(() => (completed.value ? job.value?.projectId ?? null : null))
  const running = computed(() => status.value !== null && !completed.value && !failed.value)

  function stopPolling(): void {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function applyRun(run: GraphDuplicateRun): void {
    status.value = run.status
    progress.value = { percent: run.progress, message: run.message }
    if (isGraphDuplicateTerminal(run.status)) stopPolling()
  }

  function schedule(mySeq: number): void {
    stopPolling()
    if (status.value === null || isGraphDuplicateTerminal(status.value)) return
    timer = setTimeout(() => void poll(mySeq), pollMs)
  }

  async function poll(mySeq: number): Promise<void> {
    const current = job.value
    if (!current) return
    try {
      const run = await getGraphDuplicateRun(current.runId)
      if (mySeq !== seq) return
      applyRun(run)
    } catch (caught) {
      if (mySeq !== seq) return
      // Ein Lesefehler beendet den Auftrag nicht: der Zustand ist schlicht
      // unbekannt. Der Fehler steht sichtbar da, das Polling läuft weiter.
      error.value = classify(caught)
      busy.value = false
    }
    schedule(mySeq)
  }

  /**
   * Startet den Kopierauftrag. Liefert `false`, wenn schon einer für diesen
   * Graphen läuft (kein zweiter Auftrag, keine zweite Kopie).
   */
  async function start(name: string): Promise<boolean> {
    const id = toValue(graphId)
    if (!id) {
      error.value = { kind: 'other', message: 'graph_id fehlt' }
      return false
    }
    if (busy.value || running.value) return false

    const mySeq = ++seq
    stopPolling()
    error.value = null
    progress.value = { percent: 0, message: '' }
    busy.value = true
    try {
      const created = await duplicateGraph(id, { name })
      if (mySeq !== seq) return false
      job.value = { graphId: id, projectId: created.project_id, runId: created.run_id }
      status.value = created.status
      progress.value = { percent: created.progress, message: created.message }
      // Sofort terminal (etwa bei einer Wiederholung mit gleicher Kennung):
      // dann wird nicht gepollt.
      if (isGraphDuplicateTerminal(created.status)) stopPolling()
      else schedule(mySeq)
      return true
    } catch (caught) {
      if (mySeq !== seq) return false
      error.value = classify(caught)
      job.value = null
      status.value = null
      return false
    } finally {
      if (mySeq === seq) busy.value = false
    }
  }

  /** Bricht das Polling ab und räumt den Zustand weg (Ansicht verlassen). */
  function dispose(): void {
    seq += 1
    stopPolling()
  }

  function clearError(): void {
    error.value = null
  }

  // Der Auftrag gehört zu einem Graphen. Wechselt `graph_id` (etwa weil die
  // Bibliothek einen anderen Graphen öffnet), gehören Zustand und Zieladresse
  // des alten Auftrags nicht mehr zu dem, was angezeigt wird — sonst hinge die
  // Ansicht am Ende an einem „Kopie fertig“ zu einem fremden Graphen.
  watch(
    () => toValue(graphId),
    () => {
      dispose()
      job.value = null
      status.value = null
      progress.value = { percent: 0, message: '' }
      error.value = null
      busy.value = false
    },
  )

  if (getCurrentScope()) onScopeDispose(dispose)

  return {
    job,
    status,
    progress,
    error,
    busy,
    running,
    completed,
    failed,
    copyProjectId,
    start,
    clearError,
    dispose,
  }
}

export type GraphDuplicate = ReturnType<typeof useGraphDuplicate>
