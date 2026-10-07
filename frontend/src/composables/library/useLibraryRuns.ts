import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { listReports } from '../../api/report'
import { onListInvalidated } from '../../realtime/listInvalidation'
import { useShellStore } from '../../stores/shell'
import { usePolling } from '../usePolling'
import { useShelf } from '../useShelf'
import { parseReportVersions, type ReportVersion } from './reportVersions'
import { buildRunEntries, filterRuns, parseRunsView, type RunEntry, type RunsView } from './runState'

/**
 * Datenschicht der Bibliothek der Laeufe (#1797, Bauplan 4.1).
 *
 * Quelle ist die Ablage-Aggregation (`useShelf`): keine neuen Endpunkte, keine
 * zweite Gruppierungslogik. Neu sind nur Ansicht (Kacheln/Liste, gemerkt),
 * Filter aus `?view=`, Mehrfachauswahl und das Nachladen der Fassungen.
 */

export type RunsLayout = 'tiles' | 'list'

export const LAYOUT_STORAGE_KEY = 'agora.library.runs.layout'

function loadLayout(): RunsLayout {
  try {
    return localStorage.getItem(LAYOUT_STORAGE_KEY) === 'list' ? 'list' : 'tiles'
  } catch {
    return 'tiles'
  }
}

export interface VersionsState {
  loading: boolean
  error: boolean
  versions: ReportVersion[]
  invalid: number
}

const RUNNING_POLL_MS = 10_000

export function useLibraryRuns() {
  const { t, te } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const shell = useShellStore()
  const shelf = useShelf(t, te)

  const entries = computed<RunEntry[]>(() => buildRunEntries(shelf.objects.value))
  const view = computed<RunsView>(() => parseRunsView(route.query.view))
  const visible = computed(() => filterRuns(entries.value, view.value))

  const viewCounts = computed(() => ({
    all: entries.value.length,
    running: filterRuns(entries.value, 'running').length,
    attention: filterRuns(entries.value, 'attention').length,
    'with-report': filterRuns(entries.value, 'with-report').length,
  }))

  /** Band „Im Blick“: nur sichtbar, wenn etwas laeuft oder Aufmerksamkeit braucht. */
  const running = computed(() => filterRuns(entries.value, 'running'))
  const attention = computed(() => filterRuns(entries.value, 'attention'))
  const showBand = computed(() => running.value.length > 0 || attention.value.length > 0)

  /** Erst geladen, dann „leer“ — vorher waere der Leerzustand eine Luege. */
  const loaded = ref(false)
  const isEmpty = computed(() => loaded.value && entries.value.length === 0)

  function setView(next: RunsView): void {
    const query = { ...route.query }
    if (next === 'all') delete query.view
    else query.view = next
    void router.replace({ name: route.name ?? 'LibraryRuns', params: route.params, query })
  }

  // ── Ansicht Kacheln/Liste ───────────────────────────────────────────
  const layout = ref<RunsLayout>(loadLayout())
  function setLayout(next: RunsLayout): void {
    layout.value = next
    try {
      localStorage.setItem(LAYOUT_STORAGE_KEY, next)
    } catch {
      // Private Tabs/Quota: die Wahl gilt dann nur fuer diese Sitzung.
    }
  }

  // ── Mehrfachauswahl (Reihenfolge der Markierung bleibt erhalten) ──────
  const selection = ref<string[]>([])
  function isSelected(id: string): boolean {
    return selection.value.includes(id)
  }
  function toggleSelect(id: string): void {
    selection.value = isSelected(id) ? selection.value.filter((s) => s !== id) : [...selection.value, id]
  }
  function clearSelection(): void {
    selection.value = []
  }
  const selectedEntries = computed(() =>
    selection.value.map((id) => entries.value.find((e) => e.lauf.id === id)).filter((e): e is RunEntry => Boolean(e)),
  )
  /** „Vergleichen“ gibt es erst bei genau zwei markierten Laeufen. */
  const canCompare = computed(() => selectedEntries.value.length === 2)
  /**
   * Die Vergleichsansicht (`CompareView`) nimmt genau eine `simulationId` und
   * vergleicht deren Zweige; einen zweiten Lauf kennt sie nicht. Uebergeben
   * wird deshalb der erste markierte Lauf.
   */
  const compareSimulationId = computed(() => selectedEntries.value[0]?.simulationId ?? null)

  // ── Fassungen je Lauf (GET /api/report/list?simulation_id=…) ──────────
  const versions = reactive<Record<string, VersionsState>>({})
  const openVersions = ref<string[]>([])

  async function loadVersions(entry: RunEntry): Promise<void> {
    const id = entry.lauf.id
    versions[id] = { loading: true, error: false, versions: [], invalid: 0 }
    const simulationId = entry.reports[0]?.simulationId ?? entry.simulationId
    if (!simulationId) {
      versions[id] = { loading: false, error: true, versions: [], invalid: 0 }
      return
    }
    try {
      const result = parseReportVersions(await listReports({ simulation_id: simulationId }))
      versions[id] = result.ok
        ? { loading: false, error: false, versions: result.versions, invalid: result.invalid }
        : { loading: false, error: true, versions: [], invalid: 0 }
    } catch {
      versions[id] = { loading: false, error: true, versions: [], invalid: 0 }
    }
  }

  function isVersionsOpen(id: string): boolean {
    return openVersions.value.includes(id)
  }
  function toggleVersions(entry: RunEntry): void {
    const id = entry.lauf.id
    if (isVersionsOpen(id)) {
      openVersions.value = openVersions.value.filter((o) => o !== id)
      return
    }
    openVersions.value = [...openVersions.value, id]
    void loadVersions(entry)
  }

  // ── Laden, Polling, Realtime ──────────────────────────────────────────
  async function reload(): Promise<void> {
    await shelf.reload()
    loaded.value = true
    // Die Seitenleiste soll nicht ein zweites Mal denselben Stand laden muessen.
    shell.shelfSnapshot = { objects: shelf.objects.value, unavailable: shelf.unavailableSources.value }
    // Aufgeklappte Fassungslisten bleiben aktuell, wenn ein neuer Bericht entstanden ist.
    for (const id of openVersions.value) {
      const entry = entries.value.find((e) => e.lauf.id === id)
      if (entry) void loadVersions(entry)
    }
  }

  const polling = usePolling(reload, RUNNING_POLL_MS, { immediate: false })
  watch(
    () => running.value.length > 0,
    (any) => {
      if (any) void polling.start()
      else polling.stop()
    },
    { immediate: true },
  )
  onMounted(() => {
    void reload()
  })
  onBeforeUnmount(() => polling.stop())
  onListInvalidated(['projects', 'runs', 'reports'], () => {
    void reload()
  })

  // Ausgewaehlte Laeufe, die verschwinden (Filter, Neuladen), nicht still weitertragen.
  watch(entries, (list) => {
    const ids = new Set(list.map((e) => e.lauf.id))
    if (selection.value.some((s) => !ids.has(s))) selection.value = selection.value.filter((s) => ids.has(s))
  })

  return {
    entries,
    visible,
    view,
    viewCounts,
    running,
    attention,
    showBand,
    loaded,
    isEmpty,
    loading: shelf.loading,
    error: shelf.error,
    layout,
    setLayout,
    setView,
    selection,
    isSelected,
    toggleSelect,
    clearSelection,
    selectedEntries,
    canCompare,
    compareSimulationId,
    versions,
    isVersionsOpen,
    toggleVersions,
    reload,
  }
}
