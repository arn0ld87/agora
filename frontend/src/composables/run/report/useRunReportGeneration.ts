/**
 * Erzeugung eines Berichts im Bericht-Reiter (Etappe 5, #1804).
 *
 * Dünne Hülle um `useReportGeneration` (Statusmaschine, Polling von
 * `generate/status`, Start/Neustart): sie bindet es nicht an die alte Route
 * (`Step4Report`), sondern an Getter, und führt die beiden Protokoll-Ströme
 * (Agent, Konsole) mit, die `ReportLiveLogPane` anzeigt. Die Hülle ist nötig,
 * weil das Original die Log-Polls dem Aufrufer überlässt; ohne sie gäbe es
 * keinen Fortschritt außerhalb des Monolithen.
 *
 * Meldungen der Statusmaschine (`addLog`) landen in `notice` (zuletzt gemeldet)
 * und bleiben damit sichtbar, statt in einem Emit zu verschwinden.
 */
import { ref, type Ref } from 'vue'
import { getAgentLog, getConsoleLog } from '@/api/report'
import { DEFAULT_REPORT_MODE, ReportModeSchema, type ReportMode } from '@/contracts/reportV3Contract'
import {
  REPORT_STATUS_POLL_INTERVAL_MS,
  useReportGeneration,
  type ReportGenerationApi,
  type ReportLifecycleStatus,
  type UseReportGenerationReturn,
} from '@/composables/useReportGeneration'
import { useIncrementalLogPolling } from '@/composables/useIncrementalLogPolling'
import { parseAgentEntry, type AgentLogEntry } from '@/utils/reportAgentLog'

const STORAGE_REPORT_MODE = 'agora.reportMode'
const CONSOLE_LOG_POLLING_INTERVAL_MS = 2000

/** Berichtsmodus wie im Bestand: gespeicherte Wahl, sonst der Standard. */
export function resolveStoredReportMode(): ReportMode {
  try {
    const raw = localStorage.getItem(STORAGE_REPORT_MODE)
    if (raw) {
      const parsed = ReportModeSchema.safeParse(raw)
      if (parsed.success) return parsed.data
    }
  } catch {
    // Speicher nicht lesbar: Standardmodus.
  }
  return DEFAULT_REPORT_MODE
}

export interface RunReportGenerationOptions {
  simulationId: () => string
  /** Echte Berichts-ID; `undefined` solange keiner existiert (Start offen). */
  reportId: () => string | undefined
  t: (key: string) => string
  te?: (key: string) => boolean
  onLifecycleChange: (status: ReportLifecycleStatus) => void
  onStarted: (reportId: string) => void
  recordSchemaError: (where: string, error: unknown) => void
  api?: Partial<ReportGenerationApi>
}

export interface RunReportGeneration extends UseReportGenerationReturn {
  agentLogs: Ref<AgentLogEntry[]>
  consoleLogs: Ref<unknown[]>
  /** Zuletzt gemeldeter Hinweis oder Fehler der Statusmaschine (z. B. Startfehler). */
  notice: Ref<string | null>
}

export function useRunReportGeneration(options: RunReportGenerationOptions): RunReportGeneration {
  const notice = ref<string | null>(null)

  const agent = useIncrementalLogPolling<unknown, AgentLogEntry>({
    fetcher: (since) => {
      const id = options.reportId()
      return id ? getAgentLog(id, since) : Promise.resolve(null)
    },
    intervalMs: REPORT_STATUS_POLL_INTERVAL_MS,
    parseLine: parseAgentEntry,
  })
  const consoleLog = useIncrementalLogPolling<unknown, unknown>({
    fetcher: (since) => {
      const id = options.reportId()
      return id ? getConsoleLog(id, since) : Promise.resolve(null)
    },
    intervalMs: CONSOLE_LOG_POLLING_INTERVAL_MS,
  })

  const generation = useReportGeneration({
    reportId: options.reportId,
    simulationId: options.simulationId,
    t: options.t,
    te: options.te,
    addLog: (message) => {
      notice.value = message
    },
    onLifecycleChange: options.onLifecycleChange,
    recordSchemaError: options.recordSchemaError,
    // Belege und Bericht lädt `useRunReport` selbst nach dem Abschluss.
    loadEvidence: async () => {},
    buildRequestOptions: () => ({ mode: resolveStoredReportMode() }),
    onStarted: options.onStarted,
    logStreams: [
      { polling: agent.polling, reset: agent.reset },
      { polling: consoleLog.polling, reset: consoleLog.reset },
    ],
    api: options.api,
  })

  return { ...generation, agentLogs: agent.lines, consoleLogs: consoleLog.lines, notice }
}
