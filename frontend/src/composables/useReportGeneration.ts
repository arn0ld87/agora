/**
 * useReportGeneration — die Report-Statusmaschine als tiefes Modul.
 *
 * Issue #1206. Vorher lag der komplette Flow inline in
 * `components/v4/steps/Step4Report.vue`: neun offene Status-Refs, eine
 * 141-Zeilen-`pollStatus()`-Statusmaschine, die Transportfehler-Zaehler aus
 * #1023 und die Koordination dreier Polling-Instanzen. Beobachtbar war das
 * nur ueber `mount()` plus sechzehn Modul-Mocks — entsprechend hat jede
 * Aenderung am Flow die 1754-Zeilen-Spec mitgezogen.
 *
 * Frontend-Gegenstueck zu `RunLifecycle` im Backend (#1204 / PR #1205):
 * dieselbe Idee, Statusmaschine hinter einem kleinen Interface, Endzustaende
 * an genau einer Stelle gefuehrt.
 *
 * Das Interface ist die Testflaeche:
 *
 *   { status, progress, report, bootstrap(), start(), stop(), regenerate() }
 *
 * Alles, was die Statusmaschine ueber ihre Umgebung wissen muss, kommt ueber
 * das Options-Objekt herein (Vorbild: `useReportExports`). Das Composable
 * greift selbst weder auf `props`, noch auf den Router, noch auf vue-i18n
 * oder das DOM zu und laesst sich daher ohne `mount()` und ohne `vi.mock`
 * betreiben — die HTTP-Aufrufe sind ueber `api` injizierbar.
 */

import { ref, type Ref } from 'vue'
import {
  generateReport as defaultGenerateReport,
  getReport as defaultGetReport,
  getReportStatus as defaultGetReportStatus,
  type GenerateReportData,
} from '../api/report'
import {
  ReportSchema,
  ReportOutlineSchema,
  type Report,
  type ReportOutline,
} from '../contracts/reportContract'
import type { ReportMode } from '../contracts/reportV3Contract'
import { usePolling, type UsePollingReturn } from './usePolling'

/** Poll-Intervall der Report-Statusabfrage. Die Log-Polls des Aufrufers
 *  takten bewusst im selben Raster (Sub-Slice J.3). */
export const REPORT_STATUS_POLL_INTERVAL_MS = 2500

/**
 * Issue #1023 (Befund B-17, P2): `pollStatus()` verschluckte Transportfehler
 * (`catch { /* swallow *\/ }`) ohne Retry-Zaehler — bei einem toten Backend
 * wartete der Nutzer auf ein Ergebnis, das laengst nicht mehr zustande kommen
 * konnte. Bei 2500 ms Poll-Intervall sind 3 aufeinanderfolgende Fehlschlaege
 * ~7,5 s: lang genug fuer eine einzelne verlorene Anfrage oder einen kurzen
 * Backend-Restart, kurz genug, dass der Nutzer nicht minutenlang auf einen
 * toten Poll starrt.
 */
export const REPORT_POLL_FAILURE_THRESHOLD = 3

/** 0 = noch nichts angestossen, 1 = laeuft, 2 = terminal. */
export type ReportPhase = 0 | 1 | 2

/** Nach aussen gemeldeter Lebenszyklus-Zustand des Report-Laufs. */
export type ReportLifecycleStatus = 'processing' | 'completed' | 'incomplete' | 'error'

/**
 * Status-Objekt des Backends. Bewusst lokal gehalten und nicht aus
 * `api/report` importiert: dort fehlt `run_id`, das seit #764 fuer
 * `/api/runs/<id>` gebraucht wird (`simulation_id` und `run_id` sind seither
 * nicht mehr identisch).
 */
export interface ReportGenerationStatusData {
  message?: string
  outline?: unknown
  sections?: Record<string, unknown>
  current_section_index?: number
  simulation_id?: string
  report_id?: string
  /** Issue #764 (Codex P1): Registry-ID des Report-Runs (report_generation). */
  run_id?: string
  status?: string
  error?: string
}

interface ApiResult {
  success?: boolean
  data?: Record<string, unknown> & {
    report_id?: string
    simulation_id?: string
  }
  error?: string
}

interface StatusApiResult {
  success?: boolean
  data?: ReportGenerationStatusData
}

/** Anteile des Generierungs-Requests, die aus der Modell- und Modusauswahl
 *  des Aufrufers stammen. */
export interface ReportRequestOptions extends Pick<GenerateReportData, 'ai_model_ref'> {
  mode: ReportMode
}

/**
 * Ein Begleit-Poll, der dem Lebenszyklus des Reports folgt (Agent- und
 * Konsolen-Log). Die Instanzen selbst bleiben beim Aufrufer, weil sie an
 * Sticky-Scroll und damit ans DOM gebunden sind; hier zaehlt nur, dass sie
 * mit der Statusmaschine zusammen starten, stoppen und zuruecksetzen.
 */
export interface ReportLogStream {
  polling: Pick<UsePollingReturn, 'start' | 'stop'>
  reset: () => void
}

/** HTTP-Seam. Default sind die echten Endpunkte; Tests reichen Fakes herein
 *  und kommen so ohne Modul-Mocks aus. */
export interface ReportGenerationApi {
  generateReport: (data: GenerateReportData) => Promise<unknown>
  getReport: (reportId: string) => Promise<unknown>
  getReportStatus: (params: { simulationId?: string; reportId?: string }) => Promise<unknown>
}

export interface UseReportGenerationOptions {
  /** Aktuelle Report-ID aus der Route; `undefined`, solange kein Lauf existiert. */
  reportId: () => string | undefined
  /** Simulations-ID aus den Props — bewusst getrennt von der aus dem Status
   *  aufgeloesten ID (`report.resolvedSimulationId`). */
  simulationId: () => string | undefined
  /** i18n-Uebersetzer des Aufrufers. Injiziert, damit die Statusmaschine
   *  ohne App-Instanz laeuft. */
  t: (key: string) => string
  addLog: (message: string) => void
  /** Meldet Lebenszyklus-Wechsel nach oben (in Step4Report ein `update-status`-Emit). */
  onLifecycleChange: (status: ReportLifecycleStatus) => void
  recordSchemaError: (where: string, error: unknown) => void
  /** Laedt die Evidenzkarte zum abgeschlossenen Report (inkl. Retry-Budget,
   *  #1188) — bleibt beim Aufrufer, weil sie dessen Anzeigezustand steuert. */
  loadEvidence: () => Promise<void>
  /** Modell- und Modusauswahl fuer Start und Regenerierung. */
  buildRequestOptions: () => ReportRequestOptions
  /** Anzeigename des gewaehlten Modells fuer die Start-Logzeile. */
  describeModel?: () => string | null
  /** Wird nach erfolgreichem Start/Regenerieren mit der neuen Report-ID
   *  aufgerufen (in Step4Report die Routen-Navigation). */
  onStarted: (reportId: string) => void
  logStreams?: ReportLogStream[]
  pollIntervalMs?: number
  api?: Partial<ReportGenerationApi>
}

export interface ReportGenerationStatus {
  phase: Ref<ReportPhase>
  /** Es liegt kein Lauf vor und der Nutzer muss den Start bestaetigen. */
  pending: Ref<boolean>
  /** Freitext-Fortschrittsmeldung des Backends. */
  message: Ref<string>
  /**
   * Roher Backend-Status: 'pending' | 'planning' | 'generating' |
   * 'incomplete' | 'completed' | 'failed'. Getrennt von `phase` gefuehrt, weil
   * 'completed' und 'incomplete' dieselbe Phase, aber unterschiedliche
   * Botschaften tragen (P2.6).
   */
  backendStatus: Ref<string>
  /** Statusabfrage schlaegt anhaltend auf Transportebene fehl (#1023). */
  transportError: Ref<boolean>
  failureCount: Ref<number>
  /** Der Lauf ist terminal (completed, incomplete oder failed). */
  isComplete: Ref<boolean>
  /** Start oder Regenerierung laeuft gerade. */
  isBusy: Ref<boolean>
}

export interface ReportGenerationProgress {
  outline: Ref<ReportOutline | null>
  sections: Ref<Record<string, unknown>>
  currentSectionIndex: Ref<number | null>
}

export interface ReportGenerationResult {
  full: Ref<Report | null>
  /** Aus dem Status aufgeloeste Simulations-ID; faellt beim Aufrufer auf die
   *  Prop zurueck. */
  resolvedSimulationId: Ref<string | null>
  /** Letztes Status-Objekt — traegt u. a. die `run_id` des Report-Laufs (#764). */
  lastStatus: Ref<ReportGenerationStatusData | null>
}

export interface UseReportGenerationReturn {
  status: ReportGenerationStatus
  progress: ReportGenerationProgress
  report: ReportGenerationResult
  /** Einstieg beim Betreten der Ansicht: einmal Status ziehen und je nach
   *  Ergebnis Polling aufnehmen, Bestaetigung anfordern oder den fertigen
   *  Report nachladen. */
  bootstrap: () => Promise<void>
  /** Startet einen neuen Report-Lauf (bestaetigter Erststart). */
  start: () => Promise<void>
  /** Startet den Report mit `force_regenerate` neu. */
  regenerate: () => Promise<void>
  /** Beendet Statusabfrage und Begleit-Polls. */
  stop: () => void
}

export function useReportGeneration(
  options: UseReportGenerationOptions
): UseReportGenerationReturn {
  const api: ReportGenerationApi = {
    generateReport: defaultGenerateReport,
    getReport: defaultGetReport,
    getReportStatus: defaultGetReportStatus,
    ...options.api,
  }
  const logStreams = options.logStreams ?? []

  const phase = ref<ReportPhase>(0)
  const pending = ref(false)
  const message = ref('')
  const backendStatus = ref<string>('')
  const failureCount = ref(0)
  const transportError = ref(false)
  const isComplete = ref(false)
  const isBusy = ref(false)

  const outline = ref<ReportOutline | null>(null)
  const sections = ref<Record<string, unknown>>({})
  const currentSectionIndex = ref<number | null>(null)

  const full = ref<Report | null>(null)
  const resolvedSimulationId = ref<string | null>(options.simulationId() || null)
  const lastStatus = ref<ReportGenerationStatusData | null>(null)

  const statusPolling = usePolling(
    () => pollStatus(),
    options.pollIntervalMs ?? REPORT_STATUS_POLL_INTERVAL_MS
  )

  function startPolling(): void {
    void statusPolling.start()
    for (const stream of logStreams) void stream.polling.start()
  }

  function stopPolling(): void {
    statusPolling.stop()
    for (const stream of logStreams) stream.polling.stop()
  }

  /**
   * Sub-Slice 2 von 5 (Issue #739): Outline aus dem Report nachziehen. Wird
   * `/report/<id>` nach dem Abschluss betreten (Direct-Goto, Reload oder
   * Regenerate-Stream), liefert der Status-Endpunkt oft kein `outline` — das
   * haengt dann nur noch am Report-Contract. Idempotent, damit eine bereits
   * gepollte Outline nicht ueberschrieben wird.
   */
  function syncOutlineFromReport(report: Report | null): void {
    if (!report?.outline || outline.value) return
    try {
      outline.value = ReportOutlineSchema.parse(report.outline)
    } catch (err) {
      options.recordSchemaError('outline', err)
    }
  }

  /**
   * Laedt den fertigen Report und die zugehoerige Evidenzkarte. Ein
   * fehlgeschlagener Abruf ist hier erwartbar (der Report ist ggf. noch nicht
   * geflusht) und bleibt folgenlos; ein Zod-Mismatch dagegen wird gemeldet.
   */
  async function loadFullReport(reportId: string): Promise<void> {
    try {
      const envelope = (await api.getReport(reportId)) as ApiResult
      if (!envelope?.success) return
      try {
        const parsed = ReportSchema.parse(envelope.data)
        full.value = parsed
        syncOutlineFromReport(parsed)
      } catch (err) {
        options.recordSchemaError('report', err)
        full.value = null
      }
      await options.loadEvidence()
    } catch {
      /* Report noch nicht geflusht — der naechste Poll bzw. Reload holt ihn nach. */
    }
  }

  /** Terminalen Zustand setzen: Phase, Lebenszyklus-Meldung, Polling-Ende. */
  function enterTerminal(status: ReportLifecycleStatus): void {
    // isComplete ist zugleich die Sperre gegen einen erneuten Polling-Einstieg
    // in `bootstrap()` nach einem Reload — sonst ersetzte "Running" den
    // erreichten Endzustand.
    isComplete.value = true
    phase.value = 2
    options.onLifecycleChange(status)
  }

  async function pollStatus(): Promise<void> {
    if (!options.reportId() && !options.simulationId()) return
    try {
      const res = (await api.getReportStatus({
        simulationId: resolvedSimulationId.value || options.simulationId(),
        reportId: options.reportId(),
      })) as StatusApiResult
      if (!res?.success || !res.data) return

      // Ein erfolgreicher Poll heilt einen zuvor sichtbar gemachten
      // Transportfehler wieder aus — die Verbindung ist zurueck.
      failureCount.value = 0
      transportError.value = false

      const st = res.data
      lastStatus.value = st
      message.value = st.message || ''
      if (st.outline) {
        try {
          outline.value = ReportOutlineSchema.parse(st.outline)
        } catch (err) {
          options.recordSchemaError('outline', err)
        }
      }
      if (st.sections) sections.value = st.sections
      currentSectionIndex.value = st.current_section_index ?? currentSectionIndex.value
      if (st.simulation_id && !resolvedSimulationId.value) {
        resolvedSimulationId.value = st.simulation_id
      }
      backendStatus.value = st.status || ''

      // Die Statusabfrage kommt auch mit reiner Simulations-ID durch; liefert
      // die Antwort dann kein `report_id`, gibt es nichts nachzuladen. Vorher
      // stand hier ein `as string`-Cast, der `getReport(undefined)` auf die
      // Reise schickte — der Fehlschlag verschwand im leeren catch und der
      // Report blieb ohne Meldung leer (CodeRabbit zu PR #1207).
      const terminalReportId = st.report_id || options.reportId()

      if (st.status === 'completed') {
        enterTerminal('completed')
        if (terminalReportId) await loadFullReport(terminalReportId)
        stopPolling()
      } else if (st.status === 'incomplete') {
        // Backend meldet fehlgeschlagene Pflichtsections. Der Rest des Reports
        // bleibt nutzbar; der Nutzer sieht, was fehlt.
        enterTerminal('incomplete')
        options.addLog(
          options.t('step4.status.incomplete') || 'Report unvollständig — einige Abschnitte fehlen.'
        )
        if (terminalReportId) await loadFullReport(terminalReportId)
        stopPolling()
      } else if (st.status === 'failed') {
        enterTerminal('error')
        options.addLog(`${options.t('errors.reportFailed')}: ${st.error || ''}`)
        stopPolling()
      } else {
        phase.value = 1
      }
    } catch {
      // Issue #1023 (Befund B-17): Transportfehler zaehlen statt schweigend
      // verwerfen. Log nur beim Ueberschreiten der Schwelle (nicht bei jedem
      // weiteren Fehlschlag danach) — sonst spammt ein anhaltend totes Backend
      // das Log mit einer Meldung pro Poll-Intervall.
      failureCount.value++
      if (failureCount.value === REPORT_POLL_FAILURE_THRESHOLD) {
        transportError.value = true
        options.addLog(options.t('step4.status.pollTransportError'))
      }
    }
  }

  /** Fortschritt auf Anfang zuruecksetzen — vor jedem neuen Lauf. */
  function resetProgress(): void {
    isComplete.value = false
    phase.value = 1
    outline.value = null
    sections.value = {}
    currentSectionIndex.value = null
    full.value = null
    for (const stream of logStreams) stream.reset()
  }

  /**
   * Gemeinsamer Rumpf von `start()` und `regenerate()`. Einziger Unterschied
   * ist `force_regenerate` und die Frage, ob ein Fehlschlag den Nutzer wieder
   * in die Startbestaetigung zurueckwirft — beim Erststart ja, beim
   * Regenerieren nein (dort steht bereits ein Report auf dem Schirm).
   */
  async function launch(opts: {
    forceRegenerate: boolean
    logPrefix: string
    missingIdMessage: string
    restorePendingOnFailure: boolean
  }): Promise<void> {
    const simId = resolvedSimulationId.value || options.simulationId()
    if (!simId) {
      options.addLog(opts.missingIdMessage)
      return
    }
    if (opts.restorePendingOnFailure) pending.value = false
    isBusy.value = true
    try {
      const requestOptions = options.buildRequestOptions()
      const payload: GenerateReportData = {
        simulation_id: simId,
        ...(opts.forceRegenerate ? { force_regenerate: true } : {}),
        ...requestOptions,
      }
      const model = options.describeModel?.() ?? null
      options.addLog(
        `${opts.logPrefix}${model ? ` mit ${model}` : ''} (Modus: ${requestOptions.mode})…`
      )
      const res = (await api.generateReport(payload)) as ApiResult
      if (res?.success && res.data?.report_id) {
        resetProgress()
        options.onLifecycleChange('processing')
        options.onStarted(res.data.report_id as string)
        startPolling()
      } else {
        options.addLog(`Fehler: ${res?.error || 'unbekannt'}`)
        if (opts.restorePendingOnFailure) pending.value = true
      }
    } catch (err) {
      options.addLog((err as Error).message)
      if (opts.restorePendingOnFailure) pending.value = true
    } finally {
      isBusy.value = false
    }
  }

  async function start(): Promise<void> {
    await launch({
      forceRegenerate: false,
      logPrefix: 'Report starten',
      missingIdMessage: 'simulationId fehlt — Report-Start nicht möglich.',
      restorePendingOnFailure: true,
    })
  }

  async function regenerate(): Promise<void> {
    await launch({
      forceRegenerate: true,
      logPrefix: 'Report neu generieren',
      missingIdMessage: 'simulationId fehlt — Regenerieren nicht möglich.',
      restorePendingOnFailure: false,
    })
  }

  async function bootstrap(): Promise<void> {
    await pollStatus()
    if (!isComplete.value) {
      if (options.reportId()) {
        phase.value = 1
        startPolling()
      } else {
        phase.value = 0
        pending.value = true
      }
      return
    }
    const reportId = options.reportId()
    if (!full.value && reportId) {
      await loadFullReport(reportId)
    }
  }

  return {
    status: {
      phase,
      pending,
      message,
      backendStatus,
      transportError,
      failureCount,
      isComplete,
      isBusy,
    },
    progress: { outline, sections, currentSectionIndex },
    report: { full, resolvedSimulationId, lastStatus },
    bootstrap,
    start,
    regenerate,
    stop: stopPolling,
  }
}
