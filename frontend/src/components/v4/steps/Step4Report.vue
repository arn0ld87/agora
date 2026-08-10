<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, type ComponentPublicInstance } from 'vue'
import { useIncrementalLogPolling } from '../../../composables/useIncrementalLogPolling'
import { useStickyScroll } from '../../../composables/useStickyScroll'
import { usePolling } from '../../../composables/usePolling'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { renderMarkdown } from '../../../utils/markdown'
import { generateReport, getAgentLog, getConsoleLog, getReport, getReportStatus, getReportEvidence } from '../../../api/report'
import type { GenerateReportData } from '../../../api/report'
import { createSimulationBranch } from '../../../api/simulation'
import { getRun } from '../../../api/runs'
import { getRunLlmRouting } from '../../../api/llmRouting'
import { useAiModelRefAdapter } from '@/composables/useAiModelRefAdapter'
import {
  RunBudgetStatusSchema,
  RunUsageSchema,
  type CostStatus,
  type RunBudgetStatus,
  type RunUsage,
  type TokensStatus,
  type UsageMetrics,
} from '../../../contracts/runBudgetContract'
import Button from '@/components/v4/forms/Button.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import ReportModelControls from '../../step4/ReportModelControls.vue'
import ReportModeControls from '../../step4/ReportModeControls.vue'
import ReportOutlinePanel from '../../step4/ReportOutlinePanel.vue'
import ReportLiveLogPane from '../../step4/ReportLiveLogPane.vue'
import ReportFinalView from '../../step4/ReportFinalView.vue'
import RunUsageBreakdown from '@/components/v4/run-budget/RunUsageBreakdown.vue'
import { useReportExports } from '../../../composables/useReportExports'
import type { AiModelRef } from '../../../contracts/aiModelRef'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import { parseAgentEntry } from '../../../utils/reportAgentLog'
import { parseSourceAnchor } from '../../../utils/sourceAnchor'
import { buildReportRoute, buildInteractionRoute } from '../../../utils/reportRoute'
import {
  ReportSchema,
  ReportOutlineSchema,
  EvidenceMapSchema,
  type Report,
  type ReportOutline,
  type EvidenceMap,
  type EvidenceOmission,
} from '../../../contracts/reportContract'
import {
  ReportModeSchema,
  DEFAULT_REPORT_MODE,
  type ReportMode,
} from '../../../contracts/reportV3Contract'

interface StatusData {
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
  data?: StatusData
}

const { t } = useI18n()
const router = useRouter()

const props = defineProps({
  reportId: String,
  // Issue #764 (Codex P1): Run-Registry-ID wird von Step3 als
  // ?runId=<id> weitergereicht. simulation_id und run_id sind seit #764
  // nicht mehr identisch — die Run-Registry generiert beim Start eine
  // eigene UUID, die fuer /api/runs/<id> zwingend noetig ist.
  // loadRunUsage() priorisiert runId, faellt auf simulationId zurueck.
  runId: String,
  simulationId: String,
  systemLogs: Array,
  cancelEndpointAvailable: { type: Boolean, default: false },
})

const emit = defineEmits(['add-log', 'update-status', 'stop'])

const phase = ref(0)
const reportPending = ref(false)
const statusMsg = ref('')
// Tatsaechlicher Backend-Status: 'pending' | 'planning' | 'generating' |
// 'incomplete' | 'completed' | 'failed'. Wird im Status-Poll gesetzt und
// steuert Badge-Text/Variant (P2.6: vorher fiel 'incomplete' durch den
// else-Zweig und blieb als 'running' sichtbar).
const reportStatus = ref<string>('')
// Issue #1023 (Befund B-17, P2): pollStatus() verschluckte Transportfehler
// (`catch { /* swallow */ }`) ohne Retry-Zaehler — bei einem toten Backend
// wartete der Nutzer auf ein Ergebnis, das laengst nicht mehr zustande kommen
// konnte. STATUS_POLLING_INTERVAL_MS ist 2500ms (siehe unten); 3
// aufeinanderfolgende Fehlschlaege sind ~7.5s — lang genug, um eine einzelne
// verlorene Anfrage oder einen kurzen Backend-Restart zu tolerieren, aber
// kurz genug, dass der Nutzer nicht minutenlang auf einen toten Poll starrt.
const POLL_FAILURE_THRESHOLD = 3
const pollFailureCount = ref(0)
const pollTransportError = ref(false)
const reportOutline = ref<ReportOutline | null>(null)
const generatedSections = ref<Record<string, unknown>>({})
const currentSectionIndex = ref<number | null>(null)
const isComplete = ref(false)
const fullReport = ref<Report | null>(null)
// Issue #764 (Codex P1): letztes Report-Status-Objekt, damit loadReportRunUsage
// den Report-Run (report_generation) ueber dessen run_id nachladen kann.
const lastReportStatus = ref<StatusData | null>(null)

// Issue #764: Verbrauchsübersicht zum Sim-Run, einmalig nach Abschluss
// geladen (die Simulation ist der Run — simulation_id == run_id).
// Wir halten Sim- und Report-Verbrauch in getrennten Refs, leiten den
// angezeigten `runUsage` als computed ab und mutieren dabei keine der
// beiden Quellen — damit eine Regeneration des Reports den Sim-Stand
// nicht überschreibt und Aggregationsverluste ausbleiben.
const simUsage = ref<RunUsage | null>(null)
const reportUsage = ref<RunUsage | null>(null)
const runUsageLoaded = ref(false)
const runBudget = ref<RunBudgetStatus | null>(null)

function sumOptInt(
  a: number | null | undefined,
  b: number | null | undefined,
): number | null {
  const av = typeof a === 'number' ? a : null
  const bv = typeof b === 'number' ? b : null
  if (av === null && bv === null) return null
  return (av ?? 0) + (bv ?? 0)
}

function combineCostStatus(
  a: CostStatus | undefined,
  b: CostStatus | undefined,
): CostStatus {
  // 'unknown' ist die konservativste Aussage und dominiert; 'estimated'
  // dominiert über 'measured'/'free', sobald eine Seite nur eine
  // Teilsumme liefern kann.
  if (a === 'unknown' || b === 'unknown') return 'unknown'
  if (a === 'estimated' || b === 'estimated') return 'estimated'
  if (a === 'free' || b === 'free') return 'free'
  return 'measured'
}

function combineTokensStatus(
  a: TokensStatus | undefined,
  b: TokensStatus | undefined,
): TokensStatus {
  if (a === 'unknown' || b === 'unknown') return 'unknown'
  if (a === 'partial' || b === 'partial') return 'partial'
  return 'measured'
}

const runUsage = computed<RunUsage | null>(() => {
  const sim = simUsage.value
  const rep = reportUsage.value
  if (!sim && !rep) return null
  // Baseline-Objekt kopieren (spread), damit by_stage / by_provider /
  // by_model aus genau einer Quelle stammen, die Totals aber aggregiert
  // werden. Mutationen der Quellen sind ausgeschlossen.
  const baseline: RunUsage = sim ?? (rep as RunUsage)
  const simTotals: UsageMetrics = sim?.totals ?? ({} as UsageMetrics)
  const repTotals: UsageMetrics = rep?.totals ?? ({} as UsageMetrics)
  const totals: UsageMetrics = {
    ...baseline.totals,
    input_tokens: sumOptInt(simTotals.input_tokens, repTotals.input_tokens),
    output_tokens: sumOptInt(simTotals.output_tokens, repTotals.output_tokens),
    total_tokens: sumOptInt(simTotals.total_tokens, repTotals.total_tokens),
    llm_calls:
      (simTotals.llm_calls ?? 0) + (repTotals.llm_calls ?? 0),
    cost_micros: sumOptInt(simTotals.cost_micros, repTotals.cost_micros),
    duration_ms:
      (simTotals.duration_ms ?? 0) + (repTotals.duration_ms ?? 0),
    cost_status: combineCostStatus(simTotals.cost_status, repTotals.cost_status),
    tokens_status: combineTokensStatus(
      simTotals.tokens_status,
      repTotals.tokens_status,
    ),
  }
  return { ...baseline, totals }
})

async function loadRunUsage(): Promise<void> {
  // Issue #764 (Codex P1): runId (Registry-eindeutig) hat Vorrang vor
  // resolvedSimulationId / simulationId — /api/runs/<id> erwartet die
  // Registry-ID, sonst liefert das Backend einen Run-not-found.
  const simId = props.runId || resolvedSimulationId.value || props.simulationId
  if (!simId || runUsageLoaded.value) return
  runUsageLoaded.value = true
  try {
    const envelope = await getRun(simId)
    if (!envelope?.success) return
    const raw = (envelope.data ?? {}) as unknown as Record<string, unknown>
    const usage = RunUsageSchema.nullable().safeParse(raw.usage ?? null)
    simUsage.value = usage.success ? usage.data : null
    const budget = RunBudgetStatusSchema.nullable().safeParse(raw.budget ?? null)
    runBudget.value = budget.success ? budget.data : null
  } catch { /* Verbrauchsdaten sind optional — Report bleibt nutzbar */ }
}

// Issue #764 (Codex P1): der Report-Workflow hat einen eigenen Run
// (report_generation), der den weichen/harten Budget-Limits unterliegt
// und ueber getReportStatus geliefert wird. Wir laden seinen Verbrauch
// nach Abschluss zusaetzlich in `reportUsage` — das `runUsage`-Computed
// uebernimmt die ehrliche Aggregation aus beiden Quellen.
async function loadReportRunUsage(): Promise<void> {
  const st = lastReportStatus.value as StatusData | null
  const reportRunId = st?.run_id
  if (!reportRunId) return
  try {
    const envelope = await getRun(reportRunId)
    if (!envelope?.success) return
    const raw = (envelope.data ?? {}) as unknown as Record<string, unknown>
    const usage = RunUsageSchema.nullable().safeParse(raw.usage ?? null)
    if (!usage.success || !usage.data) return
    reportUsage.value = usage.data
  } catch { /* Report-Run ist optional */ }
}

// Sobald der Report terminal ist (completed/incomplete/failed), einmalig
// die Abschluss-Verbrauchsdaten ziehen. Sim-Ladevorgang zuerst, damit
// der Report-Verbrauch nicht in einen leeren Baseline aggregiert wird
// (sonst wirken spaetere Regenerationen wie sprunghafte Zahlen).
watch(isComplete, async (done) => {
  if (!done) return
  await loadRunUsage()
  await loadReportRunUsage()
})
const evidenceMap = ref<EvidenceMap | null>(null)
const selectedEvidenceSection = ref<number | null>(null)
const branchBusy = ref(false)
const schemaError = ref<{ where: string; issues: string[] } | null>(null)

function recordSchemaError(where: string, error: unknown): void {
  const issues =
    error &&
    typeof error === 'object' &&
    'issues' in (error as object) &&
    Array.isArray((error as { issues: unknown }).issues)
      ? (error as { issues: Array<{ path: unknown[]; message: string }> }).issues.map(
          (i) => `${i.path.length ? i.path.join('.') : '<root>'}: ${i.message}`
        )
      : [String((error as { message?: string } | null)?.message ?? error)]
  schemaError.value = { where, issues }
  console.error(`[Step4Report] Schema-Mismatch in ${where}:`, issues)
}

// Issue #987: Der JSON-Export kann ohne Evidence-Map ausgeliefert werden.
// Der Hinweis wird gerendert, nicht geloggt — addLog() emittiert hier nur
// ein `add-log`, auf das der produktive Mount (StepReportView.vue) nicht
// hoert. Der Text kommt aus vue-i18n; der Vertrag liefert dafuer den
// stabilen Schluessel `reason`, nicht den Anzeigetext.
const evidenceOmission = ref<EvidenceOmission | null>(null)

function recordEvidenceOmission(omission: EvidenceOmission | null): void {
  evidenceOmission.value = omission
  if (omission) {
    console.warn('[Step4Report] Evidence-Map fehlt im JSON-Export:', omission)
  }
}

const resolvedSimulationId = ref(props.simulationId || null)
// Phase-1 Konsolidierung: Das Report-Modell wird aus dem Kanon
// (routing/defaults.global via useEffectiveModelSelection) initialisiert, nicht
// mehr aus einem eigenen agora.report.aiModelRef-Key. Ein Picker-Pick ist ein
// transienter Report-Override (nur diese Regenerierung), nicht persistiert.
// Slice 7.6c (Storage-Cut): Legacy-Key agora.report.route wird defensiv entfernt.
const STORAGE_REPORT_ROUTE_LEGACY = 'agora.report.route'

const effectiveModel = useEffectiveModelSelection()
const aiModelRefAdapter = useAiModelRefAdapter()

/**
 * Issue #1023 (Befund B-26, P1): der Anzeige-Default fuer das Report-Modell
 * kam bisher ausschliesslich aus dem Workspace-Kanon
 * (useEffectiveModelSelection), nie aus dem fuer DIESEN Lauf gewaehlten
 * Modell. Nutzt denselben Weg wie StepModelOverrideChip.vue (Teilpunkt 3,
 * #1023): GET /api/runs/<id>/llm-routing.
 *
 * Reihenfolge: Snapshot der Stage (falls report_generation in diesem Lauf
 * schon einmal gelaufen ist, z. B. Regenerierung) > vom Lauf konfigurierte
 * Stage-Route/Global-Default (RuntimeLlmRouting) > null (Aufrufer faellt
 * auf den Workspace-Kanon zurueck).
 *
 * Der Rueckgabewert ist Anzeige-Default UND Request-Override (siehe
 * `runModelDefault` und `buildModelSelection()`). Anders als beim
 * Workspace-Kanon, den das Backend ohnehin selbst zieht, kennt der Server das
 * Lauf-Modell an dieser Stelle nicht: `ReportGenerationService.start_generation()`
 * legt einen neuen Report-Lauf an und seedet ihn aus dem Request. Wuerde die UI
 * das Lauf-Modell nur anzeigen, liefe der Report unter dem Workspace-Default —
 * die Anzeige und das Start-Log nennten ein Modell, das nicht zum Einsatz kommt.
 */
async function loadRunModelDefault(runId: string): Promise<AiModelRef | null> {
  try {
    const response = await getRunLlmRouting(runId)
    const snapshot = response.snapshots?.report_generation
    if (snapshot?.model) {
      return aiModelRefAdapter.toAiModelRef({
        stage: 'report_generation',
        provider_id: snapshot.provider_id,
        model: snapshot.model,
        temperature: null,
        max_tokens: null,
        reasoning_effort: snapshot.reasoning_effort ?? 'none',
        provider_options: {},
      })
    }
    const runtimeConfig = response.runtime_config
    const runtimeRoute = runtimeConfig?.stage_overrides?.report_generation
      ?? runtimeConfig?.global_default
      ?? null
    if (runtimeRoute?.model) {
      return aiModelRefAdapter.toAiModelRef(runtimeRoute)
    }
  } catch {
    // Lauf-Routing (noch) nicht abrufbar — Workspace-Kanon bleibt Fallback.
  }
  return null
}

const reportRoute = ref<AiModelRef | null>(null)
// Expliziter Nutzer-Pick — strikt getrennt vom Anzeige-Default. Der beim Mount
// aus dem Kanon (routing/defaults.global_default) übernommene Wert befüllt nur
// reportRoute (Anzeige) und darf keinen Request-Override erzeugen.
const reportRouteOverride = ref<AiModelRef | null>(null)
// Das Modell dieses Laufs (aus /api/runs/<id>/llm-routing). Es befüllt die
// Anzeige wie der Kanon-Default, geht aber zusätzlich in den Start-Request:
// der Server kennt es beim Anlegen des Report-Laufs nicht von selbst.
const runModelDefault = ref<AiModelRef | null>(null)

function onReportRoutePicked(val: AiModelRef | null) {
  reportRoute.value = val
  reportRouteOverride.value = val
}
const isRegenerating = ref(false)

const STORAGE_REPORT_MODE = 'agora.reportMode'
function resolveStoredReportMode(): ReportMode {
  const raw = localStorage.getItem(STORAGE_REPORT_MODE)
  if (raw) {
    const parsed = ReportModeSchema.safeParse(raw)
    if (parsed.success) return parsed.data
  }
  return DEFAULT_REPORT_MODE
}
const reportMode = ref<ReportMode>(resolveStoredReportMode())
watch(reportMode, (val) => { localStorage.setItem(STORAGE_REPORT_MODE, val) })

function effectiveReportModel(): string | null {
  const m = reportRoute.value?.model_id
  return m && m.trim() ? m.trim() : null
}

/**
 * Baut die Modellauswahl für den Report-Request (Issue #817, konsolidiert in
 * Issue #834).
 *
 * Zwei Quellen erzeugen einen Override, in dieser Reihenfolge:
 *
 * 1. der explizite Picker-Pick (`reportRouteOverride`) — er gewinnt immer;
 * 2. das Modell dieses Laufs (`runModelDefault`, Issue #1023 / PR #1025).
 *
 * Der aus dem Workspace-Kanon übernommene Anzeige-Default (`reportRoute` ohne
 * die beiden oberen Quellen) erzeugt weiterhin KEINEN Override: ihn zieht das
 * Backend ohnehin selbst, und ohne echte Nutzerwahl sollen die serverseitigen
 * Stage-Defaults unverändert wirksam bleiben. Beim Lauf-Modell liegt der Fall
 * anders — `start_generation()` legt einen neuen Report-Lauf an und übernimmt
 * das Routing des Simulationslaufs nicht. Ohne den Override zeigte die UI
 * Modell A und der Report liefe unter B.
 *
 * Der Legacy-Profil-Zweig (`llm_profile_id` über v3-Profil-Legacy-Picker) wurde
 * mit Issue #834 entfernt — es gibt nur noch genau eine Auswahlsenke
 * (`ai_model_ref`).
 */
function sameModelRef(a: AiModelRef | null, b: AiModelRef | null): boolean {
  if (!a || !b) return false
  return a.provider_connection_id === b.provider_connection_id && a.model_id === b.model_id
}

function buildModelSelection(): Pick<GenerateReportData, 'ai_model_ref'> {
  const picked = reportRouteOverride.value
  // Das Lauf-Modell geht nur mit, solange die Anzeige es auch zeigt. Waehlt der
  // Nutzer im Picker ab (reportRoute wird null), darf der Request nicht heimlich
  // beim Lauf-Modell bleiben — Anzeige und Ausfuehrung sind hier dasselbe
  // Versprechen.
  const runModel = sameModelRef(reportRoute.value, runModelDefault.value)
    ? runModelDefault.value
    : null
  const selected = picked ?? runModel
  if (!selected) return {}
  return {
    ai_model_ref: {
      provider_connection_id: selected.provider_connection_id,
      model_id: selected.model_id,
      // Ohne Picker-Pick ist die Herkunft der Lauf-Kontext, nicht eine
      // Nutzerentscheidung — llm_routing_seed schreibt sie so ins Run-Log.
      source: picked ? (picked.source ?? 'explicit') : 'run-override',
      // Issue #901: den vom Picker gelieferten Grund weiterreichen. Ohne ihn
      // schreibt llm_routing_seed._fallback_reason_for den Platzhalter
      // unspecified_fallback, obwohl die Ursache bekannt war.
      ...(selected.fallback_reason ? { fallback_reason: selected.fallback_reason } : {}),
    },
  }
}

// PR #975 (CodeRabbit): Beim Start und beim Regenerieren wechselt die Route
// auf die neue reportId. Ohne den ?runId=<id>-Query verliert StepReportView
// die Registry-Run-ID und Step4Report faellt auf simulationId zurueck —
// /api/runs/<simulation_id> ist aber nicht dieselbe ID (siehe props.runId).
function reportNavigationTarget(reportId: string) {
  return buildReportRoute(reportId, props.runId)
}

async function regenerateWithModel() {
  const simId = resolvedSimulationId.value || props.simulationId
  if (!simId) { addLog('simulationId fehlt — Regenerieren nicht möglich.'); return }
  isRegenerating.value = true
  try {
    const payload: GenerateReportData = {
      simulation_id: simId,
      force_regenerate: true,
      mode: reportMode.value,
      ...buildModelSelection(),
    }
    const m = effectiveReportModel()
    addLog(`Report neu generieren${m ? ` mit ${m}` : ''} (Modus: ${reportMode.value})…`)
    const res = (await generateReport(payload)) as ApiResult
    if (res?.success && res.data?.report_id) {
      isComplete.value = false; phase.value = 1; reportOutline.value = null
      generatedSections.value = {}; currentSectionIndex.value = null
      resetAgentLogs(); resetConsoleLogs(); fullReport.value = null
      emit('update-status', 'processing')
      router.push(reportNavigationTarget(res.data.report_id as string))
      startPolling()
    } else { addLog(`Fehler: ${res?.error || 'unbekannt'}`) }
  } catch (err) { addLog((err as Error).message) }
  finally { isRegenerating.value = false }
}

async function startReportConfirmed() {
  const simId = resolvedSimulationId.value || props.simulationId
  if (!simId) { addLog('simulationId fehlt — Report-Start nicht möglich.'); return }
  reportPending.value = false
  isRegenerating.value = true
  try {
    const payload: GenerateReportData = {
      simulation_id: simId,
      mode: reportMode.value,
      ...buildModelSelection(),
    }
    const m = effectiveReportModel()
    addLog(`Report starten${m ? ` mit ${m}` : ''} (Modus: ${reportMode.value})…`)
    const res = (await generateReport(payload)) as ApiResult
    if (res?.success && res.data?.report_id) {
      isComplete.value = false; phase.value = 1; reportOutline.value = null
      generatedSections.value = {}; currentSectionIndex.value = null
      resetAgentLogs(); resetConsoleLogs(); fullReport.value = null
      emit('update-status', 'processing')
      router.push(reportNavigationTarget(res.data.report_id as string))
      startPolling()
    } else { addLog(`Fehler: ${res?.error || 'unbekannt'}`); reportPending.value = true }
  } catch (err) { addLog((err as Error).message); reportPending.value = true }
  finally { isRegenerating.value = false }
}

function addLog(msg: string) { emit('add-log', msg) }

const STATUS_POLLING_INTERVAL_MS = 2500
const AGENT_LOG_POLLING_INTERVAL_MS = STATUS_POLLING_INTERVAL_MS
const CONSOLE_LOG_POLLING_INTERVAL_MS = 2000

const statusPolling = usePolling(pollStatus, STATUS_POLLING_INTERVAL_MS)

const agentLogRef = ref<HTMLElement | null>(null)
const consoleLogRef = ref<HTMLElement | null>(null)
const agentSticky = useStickyScroll(agentLogRef)
const consoleSticky = useStickyScroll(consoleLogRef)

function setAgentLogRef(el: Element | ComponentPublicInstance | null) {
  agentLogRef.value = el instanceof Element ? (el as HTMLElement) : null
}
function setConsoleLogRef(el: Element | ComponentPublicInstance | null) {
  consoleLogRef.value = el instanceof Element ? (el as HTMLElement) : null
}

const {
  lines: agentLogs,
  polling: agentLogPolling,
  reset: resetAgentLogs,
} = useIncrementalLogPolling({
  fetcher: (sinceLine) => props.reportId ? getAgentLog(props.reportId, sinceLine) : Promise.resolve(null),
  intervalMs: AGENT_LOG_POLLING_INTERVAL_MS,
  parseLine: parseAgentEntry,
  stickyScroll: agentSticky,
})

const {
  lines: consoleLogs,
  polling: consoleLogPolling,
  reset: resetConsoleLogs,
} = useIncrementalLogPolling({
  fetcher: (sinceLine) => props.reportId ? getConsoleLog(props.reportId, sinceLine) : Promise.resolve(null),
  intervalMs: CONSOLE_LOG_POLLING_INTERVAL_MS,
  stickyScroll: consoleSticky,
})

async function pollStatus() {
  if (!props.reportId && !props.simulationId) return
  try {
    const res = (await getReportStatus({
      simulationId: resolvedSimulationId.value || props.simulationId,
      reportId: props.reportId,
    })) as StatusApiResult
    if (res?.success && res.data) {
      // Ein erfolgreicher Poll heilt einen zuvor sichtbar gemachten
      // Transportfehler wieder aus — die Verbindung ist zurueck.
      pollFailureCount.value = 0
      pollTransportError.value = false
      const st = res.data
      lastReportStatus.value = st
      statusMsg.value = st.message || ''
      if (st.outline) { try { reportOutline.value = ReportOutlineSchema.parse(st.outline) } catch (err) { recordSchemaError('outline', err) } }
      if (st.sections) generatedSections.value = st.sections
      currentSectionIndex.value = st.current_section_index ?? currentSectionIndex.value
      if (st.simulation_id && !resolvedSimulationId.value) resolvedSimulationId.value = st.simulation_id
      // P2.6: Backend-Status separat merken — er treibt das Badge und die
      // 'incomplete'-Transition. 'completed' und 'incomplete' sind beide
      // Endzustände mit unterschiedlicher User-Botschaft.
      reportStatus.value = st.status || ''
      if (st.status === 'completed') {
        const resolvedId = (st.report_id || props.reportId) as string
        isComplete.value = true; phase.value = 2
        emit('update-status', 'completed')
        try {
          const full = (await getReport(resolvedId)) as ApiResult
          if (full?.success) {
            try {
              const parsed = ReportSchema.parse(full.data)
              fullReport.value = parsed
              syncOutlineFromReport(parsed)
            } catch (err) { recordSchemaError('report', err); fullReport.value = null }
            await loadEvidence()
          }
        } catch { /* report not yet flushed */ }
        stopPolling()
      } else if (st.status === 'incomplete') {
        // Backend liefert fehlgeschlagene Pflichtsections → INCOMPLETE.
        // Rest des Reports ist nutzbar; der Nutzer sieht, was fehlt.
        const resolvedId = (st.report_id || props.reportId) as string
        // INCOMPLETE ist terminal: isComplete verhindert, dass onMounted nach
        // einem Reload erneut in den Polling-Pfad springt.
        isComplete.value = true; phase.value = 2
        emit('update-status', 'incomplete')
        addLog(t('step4.status.incomplete') || 'Report unvollständig — einige Abschnitte fehlen.')
        try {
          const full = (await getReport(resolvedId)) as ApiResult
          if (full?.success) {
            try {
              const parsed = ReportSchema.parse(full.data)
              fullReport.value = parsed
              syncOutlineFromReport(parsed)
            } catch (err) { recordSchemaError('report', err); fullReport.value = null }
            await loadEvidence()
          }
        } catch { /* report not yet flushed */ }
        stopPolling()
      } else if (st.status === 'failed') {
        // FAILED ist terminal: isComplete verhindert, dass onMounted nach
        // einem Reload erneut in den Polling-Pfad springt und den
        // "Failed"-Zustand durch "Running" ersetzt (analog zu
        // completed/incomplete).
        isComplete.value = true; phase.value = 2
        emit('update-status', 'error')
        addLog(`${t('errors.reportFailed')}: ${st.error || ''}`)
        stopPolling()
      } else { phase.value = 1 }
    }
  } catch {
    // Issue #1023 (Befund B-17): Transportfehler zaehlen statt schweigend
    // verwerfen. Log nur beim Ueberschreiten der Schwelle (nicht bei jedem
    // weiteren Fehlschlag danach) — sonst spammt ein anhaltend totes Backend
    // das Log mit einer Meldung pro Poll-Intervall.
    pollFailureCount.value++
    if (pollFailureCount.value === POLL_FAILURE_THRESHOLD) {
      pollTransportError.value = true
      addLog(t('step4.status.pollTransportError'))
    }
  }
}

function startPolling() { void statusPolling.start(); void agentLogPolling.start(); void consoleLogPolling.start() }
function stopPolling() { statusPolling.stop(); agentLogPolling.stop(); consoleLogPolling.stop() }

const reportMarkdown = computed((): string => fullReport.value?.markdown_content ?? '')
const reportHtml = computed(() => renderMarkdown(reportMarkdown.value))

// P2.6: Anzahl fehlgeschlagener Sections (generation_failed=true).
// Backend-Hinweis: jede Section kann generation_failed=true tragen, auch
// wenn der Gesamt-Report COMPLETED ist. Im INCOMPLETE-Fall zeigen wir
// die Zahl im Badge, sonst zaehlen wir sie still.
const failedSectionCount = computed((): number => {
  let n = 0
  for (const v of Object.values(generatedSections.value || {})) {
    if (v && typeof v === 'object' && (v as { generation_failed?: boolean }).generation_failed) {
      n++
    }
  }
  return n
})

const reportBadgeLabel = computed((): string => {
  if (phase.value !== 2) {
    return phase.value === 1 ? t('common.running') : t('common.ready')
  }
  if (reportStatus.value === 'failed') return t('common.failed')
  if (reportStatus.value === 'incomplete') return t('common.incomplete')
  return t('common.completed')
})

const reportBadgeTone = computed((): 'blue' | 'orange' | 'green' | 'gray' | 'red' => {
  if (phase.value !== 2) return 'blue'
  if (reportStatus.value === 'failed') return 'red'
  if (reportStatus.value === 'incomplete') return 'orange'
  return 'green'
})
const redTeamFindings = computed((): string[] => fullReport.value?.red_team_findings ?? [])

const sectionHtml = computed((): Record<string, string> => {
  const map: Record<string, string> = {}
  for (const [k, v] of Object.entries(generatedSections.value || {})) {
    const text = (v && typeof v === 'object')
      ? ((v as Record<string, unknown>).content as string || '')
      : (typeof v === 'string' ? v : '')
    map[k] = renderMarkdown(text)
  }
  return map
})

const evidenceSections = computed(() => evidenceMap.value?.sections || [])
const evidenceIndex = computed(() => evidenceMap.value?.evidence_index || {})

function navigateToAnchor(anchor: string | null | undefined) {
  const parsed = parseSourceAnchor(anchor)
  if (!parsed) return
  if (parsed.kind === 'agent-log' && parsed.entryId) {
    const target = document.getElementById(`agent-entry-${parsed.entryId}`)
    if (target) { target.scrollIntoView({ behavior: 'smooth', block: 'center' }); target.classList.add('is-highlighted'); setTimeout(() => target.classList.remove('is-highlighted'), 1500) }
    return
  }
  if (parsed.kind === 'web') { window.open(parsed.url, '_blank', 'noopener,noreferrer'); return }
  if (parsed.kind === 'kg') console.info('[Step4Report] KG-Anchor noch nicht aufrufbar:', parsed.payload)
}

// Issue #1188 (Befund 3, Nachbesserung): loadEvidence() wurde bislang genau
// einmal je Abschluss-Handler aufgerufen. Schlug der Abruf fehl — z. B. weil
// die Evidenzkarte serverseitig noch in der Nachbearbeitungsphase liegt und
// die Datei zum Zeitpunkt des ersten GET noch nicht geschrieben ist — blieb
// evidenceMap fuer immer null und der Export-Button (ReportFinalView) damit
// dauerhaft im "wird erzeugt"-Zustand, ohne dass je ein zweiter Versuch
// folgte.
//
// Dimensionierung: Issue #1187 misst 178-347s Nachbearbeitung PRO Abschnitt,
// in Summe bis zu 1344s von 2285s Gesamtlaufzeit. Ein 15s-Gesamtbudget (5x
// alle 3s) verfehlt dieses Zeitfenster um zwei Groessenordnungen. Backoff
// startet bei 3s, verdoppelt sich je Fehlschlag und deckelt bei 30s, das
// Gesamtbudget betraegt 10 Minuten.
//
// Das Budget zaehlt nur, sobald der Lauf laut reportStatus terminal ist
// (completed/incomplete/failed) und die Karte trotzdem fehlt — das ist der
// fachlich echte "Karte fehlt dauerhaft"-Fall. Waehrend eines laufenden
// Laufs ist ein fehlender GET erwartbar und wird nicht gegen das Budget
// verrechnet (in der Praxis ruft nur der terminale Zweig von pollStatus()
// bzw. onMounted() loadEvidence() ueberhaupt auf).
//
// Ein Zod-Parse-Fehler ist dagegen kein transienter Zustand
// (Schema-Mismatch statt "noch nicht fertig") und wird weiterhin nicht
// retried, sondern wie zuvor als schemaError gemeldet.
const EVIDENCE_RETRY_INITIAL_DELAY_MS = 3000
const EVIDENCE_RETRY_MAX_DELAY_MS = 30000
const EVIDENCE_RETRY_BACKOFF_FACTOR = 2
const EVIDENCE_RETRY_TOTAL_BUDGET_MS = 10 * 60 * 1000
const TERMINAL_REPORT_STATUSES = new Set(['completed', 'incomplete', 'failed'])

const evidenceRetryDelayMs = ref(EVIDENCE_RETRY_INITIAL_DELAY_MS)
const evidenceRetryElapsedMs = ref(0)
// Terminaler Endzustand: Lauf abgeschlossen, Karte bleibt trotz
// ausgeschoepftem Retry-Budget dauerhaft weg. Steuert den Tooltip-Text in
// ReportFinalView — "wird noch erzeugt" waere ab hier eine Falschaussage.
const evidenceUnavailable = ref(false)
let evidenceRetryTimer: ReturnType<typeof setTimeout> | null = null

function clearEvidenceRetry(): void {
  if (evidenceRetryTimer !== null) { clearTimeout(evidenceRetryTimer); evidenceRetryTimer = null }
}

function resetEvidenceRetryState(): void {
  clearEvidenceRetry()
  evidenceRetryDelayMs.value = EVIDENCE_RETRY_INITIAL_DELAY_MS
  evidenceRetryElapsedMs.value = 0
  evidenceUnavailable.value = false
}

function scheduleEvidenceRetry(): void {
  const isTerminal = TERMINAL_REPORT_STATUSES.has(reportStatus.value)
  if (isTerminal && evidenceRetryElapsedMs.value >= EVIDENCE_RETRY_TOTAL_BUDGET_MS) {
    evidenceUnavailable.value = true
    return
  }
  clearEvidenceRetry()
  const delay = evidenceRetryDelayMs.value
  if (isTerminal) evidenceRetryElapsedMs.value += delay
  evidenceRetryDelayMs.value = Math.min(delay * EVIDENCE_RETRY_BACKOFF_FACTOR, EVIDENCE_RETRY_MAX_DELAY_MS)
  evidenceRetryTimer = setTimeout(() => { void loadEvidence() }, delay)
}

async function loadEvidence() {
  if (!props.reportId) return
  try {
    const res = (await getReportEvidence(props.reportId)) as ApiResult
    if (!res?.success) { scheduleEvidenceRetry(); return }
    const parsed = EvidenceMapSchema.parse(res.data)
    evidenceMap.value = parsed
    resetEvidenceRetryState()
    if (!selectedEvidenceSection.value && parsed.sections.length) selectedEvidenceSection.value = parsed.sections[0].section_index
  } catch (err) { recordSchemaError('evidence', err) }
}

// Sub-Slice 2 von 5 (Issue #739): synchronisiere reportOutline aus
// fullReport.outline. Wenn /report/<id> nach completed-Status betreten wird
// (Direct-Page-Goto, Refresh oder Regenerate-Stream), liefert der
// Status-Endpoint oft kein `outline`-Feld — das Outline hängt aber am
// Report-Contract. Setzt reportOutline idempotent, damit ReportOutlinePanel
// auch ohne vorherige Status-Poll-Outline-Daten rendert.
function syncOutlineFromReport(report: Report | null) {
  if (!report?.outline || reportOutline.value) return
  try {
    reportOutline.value = ReportOutlineSchema.parse(report.outline)
  } catch (err) { recordSchemaError('outline', err) }
}

const {
  copyMarkdown,
  downloadCombinedJson,
  downloadEvidence,
  downloadHtml,
  downloadMarkdown,
  printReport,
} = useReportExports({
  reportId: () => props.reportId,
  reportMarkdown,
  reportHtml,
  evidenceMap,
  addLog,
  recordSchemaError,
  recordEvidenceOmission,
})

async function createBranchFromReport(branchForm: {
  branch_name: string; llm_model: string; language: string; max_agents: string
}) {
  const simulationId = resolvedSimulationId.value || props.simulationId
  if (!simulationId || !branchForm.branch_name.trim()) return
  branchBusy.value = true
  try {
    const overrides: Record<string, unknown> = {}
    if (branchForm.llm_model.trim()) overrides.llm_model = branchForm.llm_model.trim()
    if (branchForm.language.trim()) overrides.language = branchForm.language.trim()
    if (branchForm.max_agents !== '') overrides.max_agents = Number(branchForm.max_agents)
    const res = (await createSimulationBranch(simulationId, { branch_name: branchForm.branch_name.trim(), copy_profiles: true, copy_report_artifacts: false, overrides })) as ApiResult
    if (res?.success && res.data?.simulation_id) router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id as string } })
  } catch (e) { addLog((e as Error).message) }
  finally { branchBusy.value = false }
}

function goConversation() {
  if (!props.reportId) return
  const simulationId = resolvedSimulationId.value || props.simulationId || null
  router.push(buildInteractionRoute(props.reportId, simulationId))
}

onMounted(async () => {
  // Slice 7.6c (Storage-Cut): Legacy-Route-Key einmalig defensiv entsorgen.
  localStorage.removeItem(STORAGE_REPORT_ROUTE_LEGACY)
  // Issue #1023 (Befund B-26, P1): das fuer DIESEN Lauf gewaehlte Modell hat
  // Vorrang vor dem Workspace-Kanon-Default (siehe loadRunModelDefault()).
  //
  // Beide Quellen laufen parallel und werden ueber allSettled zusammengefuehrt,
  // nicht ueber ein verschachteltes .then(): der Lauf-Default darf nicht davon
  // abhaengen, dass der Kanon-Load gelingt. Genau das war der Fall, solange die
  // Auswertung im Erfolgszweig von ensureLoaded() hing — ein fehlgeschlagener
  // Kanon-Load verwarf das erfolgreich geladene Lauf-Modell gleich mit.
  //
  // Die reportRoute-Pruefung bleibt: hat der Nutzer in der Zwischenzeit selbst
  // gewaehlt, gewinnt seine Wahl gegen jeden nachlaufenden Default.
  const runModelPromise = props.runId ? loadRunModelDefault(props.runId) : Promise.resolve(null)
  Promise.allSettled([effectiveModel.ensureLoaded(), runModelPromise]).then(
    ([, runModelResult]) => {
      const runModel = runModelResult.status === 'fulfilled' ? runModelResult.value : null
      // Auch als Request-Override merken, unabhaengig davon, ob die Anzeige
      // ihn noch uebernimmt — sonst startete ein Nutzer, der den Picker gar
      // nicht anfasst, den Report unter dem Workspace-Default.
      if (runModel) runModelDefault.value = runModel
      if (reportRoute.value) return
      reportRoute.value = runModel ?? effectiveModel.effectiveRef.value
    },
  )
  await pollStatus()
  if (!isComplete.value) {
    if (props.reportId) { phase.value = 1; startPolling() }
    else { phase.value = 0; reportPending.value = true }
  } else if (!fullReport.value) {
    try {
      const full = (await getReport(props.reportId!)) as ApiResult
      if (full?.success) {
        try {
          const parsed = ReportSchema.parse(full.data)
          fullReport.value = parsed
          syncOutlineFromReport(parsed)
        } catch (err) { recordSchemaError('report', err); fullReport.value = null }
        await loadEvidence()
      }
    } catch { /* swallow */ }
  }
})
onUnmounted(() => { stopPolling(); clearEvidenceRetry() })
</script>

<template>
  <div class="step-panel">
    <div v-if="schemaError" class="schema-error" role="alert">
      <strong>Schema-Mismatch in {{ schemaError.where }}:</strong>
      <ul>
        <li v-for="(issue, idx) in schemaError.issues" :key="idx">{{ issue }}</li>
      </ul>
    </div>
    <!-- Issue #987: Der JSON-Export ist ausgeliefert, aber ohne Evidence-Map.
         Ein Logeintrag haette den Nutzer nicht erreicht — die heruntergeladene
         Datei saehe vollstaendig aus. -->
    <div
      v-if="evidenceOmission"
      class="schema-error"
      role="alert"
      data-testid="report-evidence-omitted"
    >
      <strong>{{ t(`step4.export.evidenceOmitted.${evidenceOmission.reason}`) }}</strong>
      <ul v-if="evidenceOmission.validation_errors.length">
        <li v-for="(err, idx) in evidenceOmission.validation_errors" :key="idx">{{ err }}</li>
      </ul>
    </div>
    <div class="scroll">
      <article class="card" :class="{ 'is-active': phase === 1 }">
        <header class="card-head">
          <Kicker num="01">{{ t('step4.title') }}</Kicker>
          <div class="card-head-actions">
            <Badge :tone="reportBadgeTone" :dot="phase === 1" data-testid="report-status-badge">
              {{ reportBadgeLabel }}
            </Badge>
            <span v-if="!props.cancelEndpointAvailable" :title="t('step4.reportConfirm.stopDisabledTip')" class="stop-btn-wrap">
              <Button variant="ghost" disabled class="stop-btn">{{ t('step4.reportConfirm.stopButton') }}</Button>
            </span>
            <Button v-else variant="ghost" class="stop-btn stop-btn--active" @click="emit('stop')">{{ t('step4.reportConfirm.stopButton') }}</Button>
          </div>
        </header>
        <p class="card-desc">{{ t('step4.sub') }}</p>
        <p v-if="statusMsg" class="meta">{{ statusMsg }}</p>
        <!-- Issue #1023 (Befund B-17): Transportfehler beim Status-Polling
             sichtbar machen statt schweigend zu verschlucken. Heilt sich
             selbst aus, sobald ein Poll wieder erfolgreich ist. -->
        <p v-if="pollTransportError" class="meta meta--warn" role="alert" data-testid="report-poll-transport-error">
          {{ t('step4.status.pollTransportError') }}
        </p>
        <!-- P2.6: Anzahl fehlgeschlagener Sections sichtbar machen. Auch bei
             status=completed moeglich (z. B. wenn nur optionale Sections
             fehlschlugen) — dann Hinweis statt harte Warnung. -->
        <p v-if="failedSectionCount > 0" class="meta meta--warn" data-testid="report-failed-sections">
          {{ t('step4.status.sectionFailed') }}: {{ failedSectionCount }}
        </p>

        <div v-if="reportPending && phase === 0" class="report-confirm-block" data-testid="report-confirm-block">
          <p class="report-confirm-title">{{ t('step4.reportConfirm.title') }}</p>
          <p class="report-confirm-desc">{{ t('step4.reportConfirm.description') }}</p>
          <div class="report-confirm-actions">
            <Button variant="primary" :disabled="isRegenerating" data-testid="report-confirm-start-btn" @click="startReportConfirmed">
              {{ t('step4.reportConfirm.startButton') }}
            </Button>
          </div>
        </div>

        <ReportModelControls
          v-if="resolvedSimulationId || simulationId"
          :model-value="reportRoute"
          :is-regenerating="isRegenerating"
          @update:model-value="onReportRoutePicked"
          @regenerate="regenerateWithModel"
        />
        <ReportModeControls
          v-if="resolvedSimulationId || simulationId"
          v-model="reportMode"
          :disabled="isRegenerating || phase === 1"
        />
      </article>

      <ReportOutlinePanel
        v-if="reportOutline"
        :outline="reportOutline"
        :generated-sections="generatedSections"
        :section-html="sectionHtml"
        :current-section-index="currentSectionIndex"
        :evidence-sections="evidenceSections"
      />

      <!-- Live logs (extracted to ReportLiveLogPane) -->
      <ReportLiveLogPane
        v-if="agentLogs.length || consoleLogs.length"
        :agent-logs="agentLogs"
        :console-logs="consoleLogs"
        :agent-unread-count="agentSticky.unreadCount.value"
        :console-unread-count="consoleSticky.unreadCount.value"
        :agent-log-ref="setAgentLogRef"
        :console-log-ref="setConsoleLogRef"
        @agent-scroll-to-bottom="agentSticky.scrollToBottom"
        @console-scroll-to-bottom="consoleSticky.scrollToBottom"
      />

      <!-- Final report + conversation hand-off (extracted to ReportFinalView) -->
      <ReportFinalView
        v-if="phase === 2 && reportHtml"
        :report-html="reportHtml"
        :red-team-findings="redTeamFindings"
        :evidence-sections="evidenceSections"
        :evidence-index="evidenceIndex"
        :evidence-unavailable="evidenceUnavailable"
        :selected-evidence-section="selectedEvidenceSection"
        :resolved-simulation-id="resolvedSimulationId"
        :simulation-id="simulationId"
        :branch-busy="branchBusy"
        @update:selected-evidence-section="selectedEvidenceSection = $event"
        @navigate="navigateToAnchor"
        @create-branch="createBranchFromReport"
        @go-conversation="goConversation"
        @copy-markdown="copyMarkdown"
        @download-markdown="downloadMarkdown"
        @download-json="downloadCombinedJson"
        @download-html="downloadHtml"
        @print-report="printReport"
        @download-evidence="downloadEvidence"
      />

      <!-- Issue #764: Abschluss-Verbrauchsübersicht (Tokens/Kosten/Laufzeit) -->
      <RunUsageBreakdown
        v-if="phase === 2 && runUsage"
        :usage="runUsage"
        :budget="runBudget"
      />

      <!-- Conversation hand-off when no report yet (phase 2, no html) -->
      <article class="card" v-if="phase === 2 && !reportHtml">
        <header class="card-head">
          <Kicker num="05" accent>{{ t('step4.next') }}</Kicker>
        </header>
        <div class="actions">
          <Button variant="primary" arrow @click="goConversation">{{ t('step4.next') }}</Button>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.step-panel { height: 100%; background: var(--bg); display: flex; flex-direction: column; overflow: hidden; }
.scroll { flex: 1; overflow-y: auto; padding: var(--s-6); display: flex; flex-direction: column; gap: var(--s-5); }
.card { background: var(--bg); border: 1px solid var(--rule); border-radius: var(--r-1); padding: var(--s-5); display: flex; flex-direction: column; gap: var(--s-4); }
.card.is-active { border-color: var(--accent); }
.card-head { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--rule); padding-bottom: var(--s-3); }
.card-desc { color: var(--fg-body); margin: 0; }
.meta { color: var(--fg-muted); font-family: var(--ff-mono); font-size: 11px; }
.meta--warn { color: var(--status-warning, #b87a00); font-weight: 600; }
.actions { display: flex; gap: var(--s-3); justify-content: flex-end; }
.schema-error {
  background: color-mix(in srgb, var(--status-error, #c0392b) 10%, transparent);
  border: 1px solid var(--status-red, var(--status-error, #c0392b));
  border-radius: var(--r-6, var(--r-1));
  padding: var(--s-4);
  margin: var(--s-4) var(--s-6) 0;
  color: var(--text-primary, var(--fg));
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-14, 13px);
}
.schema-error strong { display: block; margin-bottom: var(--s-2); color: var(--status-red, var(--status-error, #c0392b)); }
.schema-error ul { margin: 0; padding-left: var(--s-4); }
.schema-error li { line-height: 1.6; }
.report-confirm-block { display: flex; flex-direction: column; gap: var(--s-3); background: var(--bg-elevated); border: 1px solid var(--accent); border-radius: var(--r-1); padding: var(--s-4); }
.report-confirm-title { font-weight: 600; color: var(--fg); margin: 0; }
.report-confirm-desc { color: var(--fg-body); margin: 0; }
.report-confirm-actions { display: flex; gap: var(--s-3); align-items: center; }
.card-head-actions { display: flex; align-items: center; gap: var(--s-3); }
.stop-btn-wrap { display: inline-flex; }
.stop-btn { color: var(--fg-muted); }
.stop-btn--active { color: var(--status-red, var(--status-error)); }
</style>
