import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { listPersonaSets } from '../api/personaSets'
import { onListInvalidated } from '../realtime/listInvalidation'
import { useShellStore, type ShelfSnapshot } from '../stores/shell'
import { useOperatorAccess } from './useOperatorAccess'
import { usePolling } from './usePolling'
import { useShelf } from './useShelf'
import type { ShelfObject, ShelfSource } from '../types/shelf'

/**
 * Zaehler der Seitenleiste (#1795): Bibliothek, Im Blick, Aktivitaet.
 *
 * Quelle ist der Ablage-Stand (`useShelf`), nicht ein eigener Endpunkt. Der
 * Stand liegt im Shell-Store: Ist die Laeufe-Bibliothek (`LibraryRuns`) oder
 * die alte Objektansicht (`ShelfObject`) offen, veroeffentlicht die Ansicht
 * ihn nach jedem Laden und die Seitenleiste laedt NICHT mit. Auf allen anderen
 * Seiten laedt die Seitenleiste selbst (beim Verlassen der Ablage und danach
 * alle `COUNTS_POLL_MS`, im Hintergrund-Tab pausiert) sowie bei einem
 * Realtime-Signal.
 *
 * `null` heisst „unbekannt“ (noch nicht geladen oder Quelle ausgefallen) —
 * nie „0“. Die Zaehler duerfen einen Ausfall nicht als leere Bibliothek zeigen.
 */

/** Job-Status, die als „laeuft gerade“ zaehlen (RunStatusSchema). `paused` laeuft nicht. */
export const RUNNING_STATUSES: readonly string[] = ['pending', 'processing']

/** Job-Status, bei denen der juengste Job eines Laufs „braucht dich“ ausloest (RunStatusSchema). */
export const ATTENTION_STATUSES: readonly string[] = ['failed', 'stopped']

/** Rohstatus eines Berichts (ReportStatusValueSchema), der „braucht dich“ ausloest: `INCOMPLETE`. */
export const ATTENTION_REPORT_STATUS = 'incomplete'

/** Beendigungsgruende mit diesem Praefix sind erschoepfte Budgets (TerminationReasonSchema). */
const BUDGET_REASON_PREFIX = 'budget_'

export const COUNTS_POLL_MS = 30_000

export interface LibraryCounts {
  laeufe: number | null
  graphen: number | null
  personasaetze: number | null
  laeuft: number | null
  brauchtDich: number | null
  aktivitaet: number | null
}

const UNKNOWN: LibraryCounts = {
  laeufe: null,
  graphen: null,
  personasaetze: null,
  laeuft: null,
  brauchtDich: null,
  aktivitaet: null,
}

function laeufe(objects: ShelfObject[]): ShelfObject[] {
  return objects.filter((o) => o.kind === 'lauf')
}

function latestStatus(lauf: ShelfObject): string | null {
  return lauf.jobs?.[0]?.status ?? null
}

/** Ein Lauf „braucht dich“: gestoppt, fehlgeschlagen, Budget erschoepft oder mit unvollstaendigem Bericht. */
function needsAttention(lauf: ShelfObject, incompleteSimulations: Set<string>): boolean {
  const latest = lauf.jobs?.[0]
  const status = latest?.status ?? null
  if (status !== null && ATTENTION_STATUSES.includes(status)) return true
  if (latest?.terminationReason?.startsWith(BUDGET_REASON_PREFIX)) return true
  // Ein Bericht gehoert ueber die Simulation zum Lauf: der Schluessel des Laufs
  // ist meist die simulation_id des juengsten Jobs, kann aber auch eine
  // project_id sein, wenn nur ein aelterer Job die Simulation traegt.
  if (incompleteSimulations.has(lauf.id)) return true
  return (lauf.jobs ?? []).some((job) => {
    const sim = job.linkedIds.simulation_id
    return typeof sim === 'string' && incompleteSimulations.has(sim)
  })
}

/** Reine Ableitung der Zaehler — getrennt vom Composable, damit sie testbar ist. */
export function deriveLibraryCounts(
  snapshot: ShelfSnapshot | null,
  personaSetCount: number | null = null,
): LibraryCounts {
  // Personasaetze kommen aus `GET /api/persona-sets`, nicht aus der Ablage
  // (die alten Vorlagen-Zeilen `kind: 'personasatz'` zaehlen nicht mit).
  if (!snapshot) return { ...UNKNOWN, personasaetze: personaSetCount }
  const missing = (...sources: ShelfSource[]): boolean => sources.some((s) => snapshot.unavailable.includes(s))
  const runs = laeufe(snapshot.objects)

  const incompleteSimulations = new Set(
    snapshot.objects
      .filter((o) => o.kind === 'bericht' && o.reportStatus === ATTENTION_REPORT_STATUS && o.simulationId)
      .map((o) => o.simulationId as string),
  )

  return {
    laeufe: missing('runs') ? null : runs.length,
    // Graphen sind nur Projekte OHNE Lauf — dafuer braucht die Zahl beide Quellen.
    graphen: missing('runs', 'projects') ? null : snapshot.objects.filter((o) => o.kind === 'graph').length,
    personasaetze: personaSetCount,
    laeuft: missing('runs')
      ? null
      : runs.filter((o) => {
          const status = latestStatus(o)
          return status !== null && RUNNING_STATUSES.includes(status)
        }).length,
    // „Unvollstaendig“ kommt aus den Berichten: ohne sie waere die Zahl zu klein.
    brauchtDich: missing('runs', 'reports') ? null : runs.filter((o) => needsAttention(o, incompleteSimulations)).length,
    // Aktivitaet = alle Jobs der Registry (Filter „Alle Jobs“ der Ablage).
    aktivitaet: missing('runs') ? null : runs.reduce((sum, o) => sum + (o.jobs?.length ?? 0), 0),
  }
}

/**
 * Simulation des juengsten Laufs, der eine hat: Ziel des Eintrags „Vergleich“.
 * Die Vergleichsansicht (`Compare`, `/compare/:simulationId?`) waehlt mit
 * Kennung den ersten Lauf vor. `null`, solange keine bekannt ist.
 */
export function latestSimulationId(snapshot: ShelfSnapshot | null): string | null {
  for (const lauf of laeufe(snapshot?.objects ?? [])) {
    for (const job of lauf.jobs ?? []) {
      const id = job.linkedIds.simulation_id
      if (typeof id === 'string' && id) return id
    }
  }
  return null
}

export function useLibraryCounts() {
  const { t, te } = useI18n()
  const route = useRoute()
  const shell = useShellStore()
  const operatorAccess = useOperatorAccess()
  const shelf = useShelf(t, te)

  // Ansichten, die den Stand selbst laden und im Shell-Store veroeffentlichen.
  const onShelf = computed(() => route.name === 'LibraryRuns' || route.name === 'ShelfObject')

  const counts = computed(() => deriveLibraryCounts(shell.shelfSnapshot, shell.personaSetCount))

  /**
   * Eine Quelle fehlt wirklich (nicht: die Persona-Bibliothek fehlt ohne
   * Betreiber-Zugang by design) oder die Personasaetze liessen sich nicht laden.
   */
  const loadFailed = computed(
    () =>
      shell.personaSetCountFailed ||
      (shell.shelfSnapshot?.unavailable ?? []).some((s) => s !== 'templates' || operatorAccess.value),
  )

  async function load(): Promise<void> {
    await Promise.all([loadShelf(), loadPersonaSets()])
  }

  async function loadShelf(): Promise<void> {
    await shelf.reload()
    shell.shelfSnapshot = { objects: shelf.objects.value, unavailable: shelf.unavailableSources.value }
  }

  async function loadPersonaSets(): Promise<void> {
    try {
      shell.personaSetCount = (await listPersonaSets()).count
      shell.personaSetCountFailed = false
    } catch {
      shell.personaSetCount = null
      shell.personaSetCountFailed = true
    }
  }

  // Die Personasatz-Bibliothek laedt und veroeffentlicht den Stand selbst.
  const onPersonaSets = computed(() => route.name === 'LibraryPersonaSets')
  const setsPolling = usePolling(loadPersonaSets, COUNTS_POLL_MS)
  watch(
    onPersonaSets,
    (on) => {
      if (on) setsPolling.stop()
      else void setsPolling.start({ immediate: true })
    },
    { immediate: true },
  )

  // Auf der Bibliothek bzw. Ablage laedt die Ansicht und veroeffentlicht den Stand; sonst laden wir.
  const polling = usePolling(loadShelf, COUNTS_POLL_MS)
  watch(
    onShelf,
    (on) => {
      if (on) polling.stop()
      else void polling.start({ immediate: true })
    },
    { immediate: true },
  )

  onListInvalidated(['projects', 'runs', 'reports'], () => {
    if (!onShelf.value) void loadShelf()
  })

  const compareSimulationId = computed(() => latestSimulationId(shell.shelfSnapshot))

  return { counts, loadFailed, compareSimulationId, reload: load }
}
