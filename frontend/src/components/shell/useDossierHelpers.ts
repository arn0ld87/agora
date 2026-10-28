import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useOperatorAccess } from '../../composables/useOperatorAccess'
import type { ShelfObject } from '../../types/shelf'
import { useCancelAction } from './useCancelAction'
import { useObjectDetail } from '../../composables/useObjectDetail'
import { useDeriveSimulation } from '../../composables/useDeriveSimulation'
import { useStartFromPersona } from '../../composables/useStartFromPersona'
import { useSystemStatus, statusErrorKey } from '../../composables/useSystemStatus'
import { formatShelfDate, jobStatusMessage, type useShelf } from '../../composables/useShelf'
import type { ConfidenceLabel } from '../../contracts/reportContract'

export const CONFIDENCE_ORDER: ConfidenceLabel[] = ['speculative', 'low', 'medium', 'high', 'verified']

export interface DossierSystemRow {
  key: string
  label: string
  ok: boolean
  hint: string
}

export function resolveOverviewHeadingKey(liveCount: number, attentionCount: number): string {
  if (liveCount > 0 && attentionCount > 0) return 'views.shelf.overview.headingBoth'
  if (liveCount > 0) return 'views.shelf.overview.headingLive'
  if (attentionCount > 0) return 'views.shelf.overview.headingAttention'
  return 'views.shelf.overview.headingIdle'
}

export function buildConfidenceEntries(
  dist: Partial<Record<ConfidenceLabel, number>> | null | undefined,
): { label: ConfidenceLabel; count: number }[] {
  if (!dist) return []
  return CONFIDENCE_ORDER.filter((label) => (dist[label] ?? 0) > 0).map((label) => ({
    label,
    count: dist[label] ?? 0,
  }))
}

export function useDossierHelpers(props: {
  object: ShelfObject | null
  shelf: ReturnType<typeof useShelf>
}) {
  const { t, te, locale } = useI18n()
  const router = useRouter()
  // Einstellungen sind Betreiber-Zustand: für Supabase-Nutzer ausgeblendet (#1617).
  const operatorAccess = useOperatorAccess()
  const cancelAction = useCancelAction()

  // Details werden erst beim Auswaehlen geholt, nicht fuer jede Zeile.
  const { detail } = useObjectDetail(
    computed(() => props.object),
    t,
  )

  const { busy: deriveBusy, derive } = useDeriveSimulation()
  const startFromPersona = useStartFromPersona()
  const startBusy = computed(() => startFromPersona.busy.value)
  const deriveError = ref('')

  // ── Uebersichtszustand (kein Objekt gewaehlt) ──────────────────────
  const attentionItems = computed(() =>
    props.shelf.objects.value.filter((o) => o.nextAction?.kind === 'warn').slice(0, 5),
  )
  const liveItems = computed(() => props.shelf.activeObjects.value)
  const recentItems = computed(() =>
    props.shelf.objects.value.filter((o) => o.active === null && o.nextAction?.kind !== 'warn').slice(0, 3),
  )

  const overviewHeadingKey = computed(() =>
    resolveOverviewHeadingKey(liveItems.value.length, attentionItems.value.length),
  )

  const systemStatus = useSystemStatus()
  onMounted(() => {
    void systemStatus.refresh()
  })

  /** Kompakter Systemstatus — nur die Quellen, die es auch bei Reachable/Unreachable meint (Ollama idle = kein Fehler, wird ausgelassen). */
  const systemRows = computed<DossierSystemRow[]>(() => {
    const s = systemStatus.status.value
    if (!s) return []
    const rows: DossierSystemRow[] = [
      {
        key: 'neo4j',
        label: t('dashboard.system.neo4j'),
        ok: s.neo4j.reachable,
        hint: s.neo4j.reachable ? '' : s.neo4j.error ? t(statusErrorKey(s.neo4j.error)) : '',
      },
    ]
    if (s.ollama.reachable !== null) {
      rows.push({
        key: 'ollama',
        label: t('dashboard.system.ollama'),
        ok: s.ollama.reachable,
        hint: s.ollama.reachable ? '' : s.ollama.error ? t(statusErrorKey(s.ollama.error)) : '',
      })
    }
    return rows
  })

  function goTo(to: NonNullable<ShelfObject['nextAction']>['to']): void {
    void router.push(to)
  }

  function openObject(obj: ShelfObject): void {
    void router.push({ name: 'ShelfObject', params: { kind: obj.kind, objectId: obj.id } })
  }

  function goToNewObject(): void {
    void router.push({ name: 'NewRun' })
  }

  /** Ableiten gibt es nur beim Bericht, und nur wenn seine Simulation bekannt ist. */
  const canDerive = computed(
    () => props.object?.kind === 'bericht' && Boolean(props.object.simulationId),
  )

  // ── Vertrauensverteilung (nur Bericht, Redesign PR 4) ──────────────
  const confidenceEntries = computed(() =>
    buildConfidenceEntries(detail.value?.confidenceDistribution),
  )

  async function onStartFromPersona(): Promise<void> {
    const obj = props.object
    if (!obj || obj.kind !== 'personasatz') return
    deriveError.value = ''
    const res = await startFromPersona.start(obj.id, t('shelf.dossier.startName', { title: obj.title }))
    if (res) router.push({ name: 'StepEnvSetup', params: { projectId: res.simulationId } })
    else deriveError.value = t('shelf.dossier.startFailed')
  }

  async function onDerive(): Promise<void> {
    const obj = props.object
    if (!obj?.simulationId) return
    deriveError.value = ''
    const res = await derive(obj.simulationId, t('shelf.dossier.deriveName', { title: obj.title }))
    if (res) {
      router.push({ name: 'StepEnvSetup', params: { projectId: res.simulationId } })
    } else {
      deriveError.value = t('shelf.dossier.deriveFailed')
    }
  }

  function openFull(): void {
    if (!props.object?.nextAction) return
    void router.push(props.object.nextAction.to)
  }

  function togglePause(active: NonNullable<ShelfObject['active']>): void {
    if (!active.simulationId) return
    if (active.status === 'paused') void cancelAction.resume(active.simulationId)
    else void cancelAction.pause(active.simulationId)
  }

  function formatUpdatedAt(iso: string): string {
    return formatShelfDate(iso, locale.value, t)
  }

  return {
    t,
    te,
    operatorAccess,
    cancelAction,
    detail,
    deriveBusy,
    startBusy,
    deriveError,
    attentionItems,
    liveItems,
    recentItems,
    overviewHeadingKey,
    systemRows,
    canDerive,
    confidenceEntries,
    goTo,
    openObject,
    goToNewObject,
    onStartFromPersona,
    onDerive,
    openFull,
    togglePause,
    formatUpdatedAt,
    jobStatusMessage,
  }
}
