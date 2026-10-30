/**
 * Daten des Bericht-Reiters (Etappe 5, #1804, Bauplan 4.6). Eine Instanz je
 * Reiter; `RunReportView` legt sie per `provide` ab, Gliederung, Lesetext,
 * Seitenspalte und Kopf lesen sie mit `useRunReportContext()`.
 *
 * SCHNITTSTELLE (andere Tickets bauen darauf, bitte nicht ohne Absprache ändern)
 *
 *   versions   VersionsState   Fassungen des Laufs, neueste zuerst
 *   report     ReportState     der gewählte Bericht
 *   evidence   EvidenceState   Belege des gewählten Berichts
 *   selectedReportId  ComputedRef<string | null>  gewählte Fassung (Adresse, sonst jüngste)
 *   selectedClaimId   Ref<string | null>          gewählter Claim (`?claim=`)
 *   selectClaim(id)                                setzt/löscht die Auswahl
 *   outline    ComputedRef<OutlineEntry[]>         Abschnitte mit Zustand
 *   reading    ComputedRef<ReadingView>            Lesetext (HTML ist sanitisiert)
 *   generation RunReportGeneration                 Erzeugung: Fortschritt, Start, Protokoll
 *   reload()                                       Fassungen, Bericht und Belege neu laden
 *   reloadSelected()                               nur Bericht und Belege neu laden
 *
 * Alle Zustände sind nach `status` diskriminiert:
 *   VersionsState  loading | ok { items, invalid } | failed { reason }
 *   ReportState    idle | loading | ok { report } | failed { kind, reason }
 *   EvidenceState  idle | loading | ok { map } | omitted { omission } | unsaved | failed { kind, reason }
 * `idle` heißt: es gibt nichts zu laden (kein Bericht gewählt, Bericht läuft noch).
 * Der Zustand gilt auch, solange eine bekannte laufende Erzeugung ihren Berichtsdatensatz
 * noch nicht angelegt hat (404 vor dem ersten Speichern, UAT-010).
 * `unsaved` ist die Antwort 404 des Evidence-Endpunkts für eine Fassung, die selbst
 * geladen wurde: für sie ist keine Evidence-Map gespeichert (unvollständige Fassung
 * ohne erzeugten Abschnitt, Altbericht). Das ist weder ein Ladefehler noch
 * `evidence_omitted`.
 * `omitted` ist die Variante `evidence_omitted` des Evidence-Endpunkts: die Belege
 * existieren, ließen sich aber nicht vertragskonform ausliefern. Sie ist nie eine
 * Datenlücke. Jede Antwort läuft durch ein Zod-Schema (`safeParse`); eine
 * Vertragsverletzung wird als `failed` mit `kind: 'contract'` sichtbar, nie still
 * toleriert.
 */
import {
  computed,
  inject,
  provide,
  ref,
  watch,
  type ComputedRef,
  type InjectionKey,
  type Ref,
} from 'vue'
import { z } from 'zod'
import {
  getReport as defaultGetReport,
  getReportEvidence as defaultGetReportEvidence,
  getReportStatus as defaultGetReportStatus,
  listReports as defaultListReports,
  type EvidenceEnvelope,
} from '@/api/report'
import {
  ReportListItemSchema,
  ReportSchema,
  type Report,
  type ReportListItem,
} from '@/contracts/reportContract'
import { PENDING_REPORT_ID } from '@/utils/reportRoute'
import type { ReportLifecycleStatus } from '@/composables/useReportGeneration'
import {
  useRunReportGeneration,
  type RunReportGeneration,
  type RunReportGenerationOptions,
} from './useRunReportGeneration'
import { deriveOutline, deriveReading, type OutlineEntry, type ReadingView } from './reportSections'
import {
  classifyEvidenceEnvelope,
  classifyEvidenceError,
  classifyReportEnvelope,
  classifyReportLoadError,
  describeReportError,
  formatSchemaIssues,
  isActiveRegistryRunForReport,
  isReportRunningStatus,
  isReportTerminalWithEvidence,
  type EvidenceState,
  type LoadFailure,
  type ReportState,
} from './reportViewState'

export type { EvidenceState, LoadFailure, ReportState }

export interface ReportVersionItem {
  reportId: string
  /** 1 = älteste Fassung. */
  number: number
  createdAt: string
  /** Rohstatus des Berichts (`ReportStatusSchema`). */
  status: string
  /** Gelaufenes Modell dieser Fassung (`llm_model`); `null`, wenn der Bericht keines belegt. */
  model: string | null
  /** Anbieter-ID des gelaufenen Modells; `null`, wenn nicht belegt. */
  providerId: string | null
}

export type VersionsState =
  | { status: 'loading' }
  | { status: 'ok'; items: ReportVersionItem[]; invalid: number }
  | { status: 'failed'; reason: string }

export interface RunReportApi {
  listReports: (params: { simulation_id?: string; limit?: number }) => Promise<unknown>
  getReport: (reportId: string) => Promise<unknown>
  getReportEvidence: (reportId: string) => Promise<EvidenceEnvelope>
}

export interface UseRunReportOptions {
  simulationId: () => string
  /** Adressparameter: Berichts-ID, `PENDING_REPORT_ID` oder `undefined` (jüngste Fassung). */
  reportId: () => string | undefined
  t: (key: string) => string
  te?: (key: string) => boolean
  /** Eine neue Fassung wurde gestartet; der Aufrufer wechselt die Adresse. */
  onStarted?: (reportId: string) => void
  api?: Partial<RunReportApi>
  generationApi?: RunReportGenerationOptions['api']
}

export interface RunReportContext {
  versions: Ref<VersionsState>
  report: Ref<ReportState>
  evidence: Ref<EvidenceState>
  selectedReportId: ComputedRef<string | null>
  selectedClaimId: Ref<string | null>
  selectClaim: (claimId: string | null) => void
  outline: ComputedRef<OutlineEntry[]>
  reading: ComputedRef<ReadingView>
  generation: RunReportGeneration
  /** Vertragsverletzungen aus der Erzeugung (Gliederung/Bericht im Status-Poll). */
  schemaError: Ref<{ where: string; issues: string[] } | null>
  reload: () => Promise<void>
  reloadSelected: () => Promise<void>
}

export const RUN_REPORT_KEY: InjectionKey<RunReportContext> = Symbol('run-report')

const ListEnvelopeSchema = z.object({
  success: z.boolean(),
  data: z.array(z.unknown()).nullish(),
  error: z.string().nullish(),
})

function versionDate(r: ReportListItem): string {
  return r.completed_at || r.created_at || ''
}

/** Fassungen aus `GET /api/report/list`: Vertragsverletzer werden gezählt, nicht gerendert. */
export function parseVersions(envelope: unknown): VersionsState {
  const outer = ListEnvelopeSchema.safeParse(envelope)
  if (!outer.success) return { status: 'failed', reason: `Vertragsbruch GET /api/report/list: ${outer.error.message}` }
  if (!outer.data.success || !outer.data.data) {
    return { status: 'failed', reason: outer.data.error || 'listReports' }
  }
  const reports: ReportListItem[] = []
  let invalid = 0
  for (const item of outer.data.data) {
    const parsed = ReportListItemSchema.safeParse(item)
    if (parsed.success) reports.push(parsed.data)
    else invalid += 1
  }
  reports.sort((a, b) => versionDate(a).localeCompare(versionDate(b)))
  const items = reports
    .map((r, i) => ({
      reportId: r.report_id,
      number: i + 1,
      createdAt: versionDate(r),
      status: r.status,
      model: r.llm_model || null,
      providerId: r.llm_provider_id || null,
    }))
    .reverse()
  return { status: 'ok', items, invalid }
}

/** Tolerant gegenüber fehlendem Provider (Einzeltests): ein ruhender, leerer Zustand. */
function inertContext(): RunReportContext {
  const noop = async (): Promise<void> => {}
  const noRef = <T>(value: T): Ref<T> => ref(value) as Ref<T>
  const generation = {
    status: {
      phase: ref(0),
      pending: ref(false),
      message: ref(''),
      backendStatus: ref(''),
      transportError: ref(false),
      failureCount: ref(0),
      isComplete: ref(false),
      isBusy: ref(false),
    },
    progress: { outline: ref(null), sections: ref({}), currentSectionIndex: ref(null) },
    report: { full: ref(null), resolvedSimulationId: ref(null), lastStatus: ref(null) },
    bootstrap: noop,
    start: noop,
    regenerate: noop,
    stop: () => {},
    agentLogs: ref([]),
    consoleLogs: ref([]),
    notice: ref(null),
  } as unknown as RunReportGeneration
  return {
    versions: noRef<VersionsState>({ status: 'loading' }),
    report: noRef<ReportState>({ status: 'idle' }),
    evidence: noRef<EvidenceState>({ status: 'idle' }),
    selectedReportId: computed(() => null),
    selectedClaimId: noRef<string | null>(null),
    selectClaim: () => {},
    outline: computed(() => []),
    reading: computed(() => ({ title: '', summary: '', mode: 'whole' as const, sections: [], wholeHtml: '' })),
    generation,
    schemaError: noRef(null),
    reload: noop,
    reloadSelected: noop,
  }
}

/** Kontext der Eltern-Ansicht; ohne Provider ein ruhender Zustand für Einzeltests. */
export function useRunReportContext(): RunReportContext {
  return inject(RUN_REPORT_KEY, null) ?? inertContext()
}

export function provideRunReport(context: RunReportContext): void {
  provide(RUN_REPORT_KEY, context)
}

export function useRunReport(options: UseRunReportOptions): RunReportContext {
  const api: RunReportApi = {
    listReports: (params) => defaultListReports(params),
    getReport: defaultGetReport,
    getReportEvidence: defaultGetReportEvidence,
    ...options.api,
  }

  const versions = ref<VersionsState>({ status: 'loading' })
  const report = ref<ReportState>({ status: 'idle' })
  const evidence = ref<EvidenceState>({ status: 'idle' })
  const selectedClaimId = ref<string | null>(null)
  const schemaError = ref<{ where: string; issues: string[] } | null>(null)
  let seq = 0
  /** Für diese Fassung läuft die Erzeugungsabfrage (Polling) gerade. */
  let generationFor: string | null = null

  const selectedReportId = computed<string | null>(() => {
    const routed = options.reportId()
    if (routed === PENDING_REPORT_ID) return null
    if (routed) return routed
    return versions.value.status === 'ok' ? (versions.value.items[0]?.reportId ?? null) : null
  })

  function recordSchemaError(where: string, error: unknown): void {
    schemaError.value = { where, issues: formatSchemaIssues(error) }
  }

  const generation = useRunReportGeneration({
    simulationId: options.simulationId,
    reportId: () => {
      const id = selectedReportId.value
      return id ?? undefined
    },
    t: options.t,
    te: options.te,
    recordSchemaError,
    onLifecycleChange: (status: ReportLifecycleStatus) => {
      if (status === 'processing') return
      generationFor = null
      void reloadSelected().then(() => loadVersions())
    },
    onStarted: (reportId) => {
      generationFor = reportId
      void loadVersions()
      options.onStarted?.(reportId)
    },
    api: options.generationApi,
  })

  async function loadVersions(): Promise<void> {
    try {
      const res = await api.listReports({ simulation_id: options.simulationId(), limit: 50 })
      versions.value = parseVersions(res)
    } catch (err) {
      versions.value = { status: 'failed', reason: describeReportError(err) }
    }
  }

  async function loadReport(id: string): Promise<ReportState> {
    try {
      const res = await api.getReport(id)
      return classifyReportEnvelope(id, res)
    } catch (err) {
      return { status: 'failed', ...classifyReportLoadError(err) }
    }
  }

  async function loadEvidence(id: string): Promise<EvidenceState> {
    try {
      const res = await api.getReportEvidence(id)
      return classifyEvidenceEnvelope(res)
    } catch (err) {
      return classifyEvidenceError(err)
    }
  }

  const getStatus = options.generationApi?.getReportStatus ?? defaultGetReportStatus

  /**
   * Kennt die Run-Registry einen laufenden Berichts-Job zu dieser Kennung? `run_id` kommt nur
   * aus dem Registry-Zweig des Backends (`report_status.py::_status_from_run_registry`); die
   * Quittung für unbekannte Kennungen (`_acknowledge_polling`) trägt keines und beweist keinen Job.
   */
  async function generationRegisteredFor(id: string): Promise<boolean> {
    try {
      const res = await getStatus({ simulationId: options.simulationId(), reportId: id })
      return isActiveRegistryRunForReport(res, id)
    } catch {
      return false
    }
  }

  /** Bericht und Belege der gewählten Fassung; startet bzw. beendet die Erzeugungsabfrage. */
  async function reloadSelected(): Promise<void> {
    const mine = ++seq
    const id = selectedReportId.value
    if (!id) {
      report.value = { status: 'idle' }
      evidence.value = { status: 'idle' }
      if (generationFor !== '') {
        generation.stop()
        generationFor = ''
        // Kein Bericht: die Statusabfrage nach Simulations-ID zeigt einen laufenden Start
        // oder bietet die Bestätigung an.
        await generation.bootstrap()
      }
      return
    }
    report.value = { status: 'loading' }
    evidence.value = { status: 'loading' }
    const loaded = await loadReport(id)
    if (mine !== seq) return
    if (loaded.status === 'failed' && loaded.kind === 'notFound') {
      // Der Datensatz entsteht erst im Worker: bis dahin ist 404 bei laufender Erzeugung erwartbar.
      const known = generationFor === id || (await generationRegisteredFor(id))
      if (mine !== seq) return
      if (known) {
        report.value = { status: 'idle' }
        evidence.value = { status: 'idle' }
        if (generationFor !== id) {
          generation.stop()
          generationFor = id
          await generation.bootstrap()
        }
        return
      }
    }
    report.value = loaded
    if (loaded.status === 'ok' && isReportTerminalWithEvidence(loaded.report.status)) {
      const ev = await loadEvidence(id)
      if (mine !== seq) return
      evidence.value = ev
    } else {
      evidence.value = { status: 'idle' }
    }
    const running = loaded.status === 'ok' && isReportRunningStatus(loaded.report.status)
    if (running && generationFor !== id) {
      generation.stop()
      generationFor = id
      await generation.bootstrap()
    } else if (!running && generationFor && generationFor !== id) {
      generation.stop()
      generationFor = null
    }
  }

  async function reload(): Promise<void> {
    versions.value = { status: 'loading' }
    await loadVersions()
    await reloadSelected()
  }

  // Fassungswechsel über die Adresse: nur Bericht und Belege neu, die Liste bleibt.
  watch(
    () => options.reportId(),
    () => {
      if (versions.value.status === 'loading') return
      void reloadSelected()
    },
  )

  function selectClaim(claimId: string | null): void {
    selectedClaimId.value = claimId
  }

  const reportData = computed(() => (report.value.status === 'ok' ? report.value.report : null))
  const evidenceSections = computed(() => (evidence.value.status === 'ok' ? evidence.value.map.sections : []))

  function outlineInput() {
    const data = reportData.value
    return {
      outline: data?.outline ?? generation.progress.outline.value,
      evidenceSections: evidenceSections.value,
      missingSections: data?.missing_sections ?? [],
      generatedSections: generation.progress.sections.value,
      reportStatus: data?.status ?? null,
    }
  }

  const outline = computed(() => deriveOutline(outlineInput()))
  const reading = computed(() =>
    deriveReading({
      ...outlineInput(),
      markdownContent: reportData.value?.markdown_content ?? '',
      fallbackTitle: options.t('views.run.report.reading.untitled'),
    }),
  )

  return {
    versions,
    report,
    evidence,
    selectedReportId,
    selectedClaimId,
    selectClaim,
    outline,
    reading,
    generation,
    schemaError,
    reload,
    reloadSelected,
  }
}
