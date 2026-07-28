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
import Button from '@/components/v4/forms/Button.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import ReportModelControls from '../../step4/ReportModelControls.vue'
import ReportModeControls from '../../step4/ReportModeControls.vue'
import ReportOutlinePanel from '../../step4/ReportOutlinePanel.vue'
import ReportLiveLogPane from '../../step4/ReportLiveLogPane.vue'
import ReportFinalView from '../../step4/ReportFinalView.vue'
import { useReportExports } from '../../../composables/useReportExports'
import type { AiModelRef } from '../../../contracts/aiModelRef'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import { parseAgentEntry } from '../../../utils/reportAgentLog'
import { parseSourceAnchor } from '../../../utils/sourceAnchor'
import {
  ReportSchema,
  ReportOutlineSchema,
  EvidenceMapSchema,
  type Report,
  type ReportOutline,
  type EvidenceMap,
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
const reportOutline = ref<ReportOutline | null>(null)
const generatedSections = ref<Record<string, unknown>>({})
const currentSectionIndex = ref<number | null>(null)
const isComplete = ref(false)
const fullReport = ref<Report | null>(null)
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

const resolvedSimulationId = ref(props.simulationId || null)
// Phase-1 Konsolidierung: Das Report-Modell wird aus dem Kanon
// (routing/defaults.global via useEffectiveModelSelection) initialisiert, nicht
// mehr aus einem eigenen agora.report.aiModelRef-Key. Ein Picker-Pick ist ein
// transienter Report-Override (nur diese Regenerierung), nicht persistiert.
// Slice 7.6c (Storage-Cut): Legacy-Key agora.report.route wird defensiv entfernt.
const STORAGE_REPORT_ROUTE_LEGACY = 'agora.report.route'

const effectiveModel = useEffectiveModelSelection()

const reportRoute = ref<AiModelRef | null>(null)
// Expliziter Nutzer-Pick — strikt getrennt vom Anzeige-Default. Der beim Mount
// aus dem Kanon (routing/defaults.global_default) übernommene Wert befüllt nur
// reportRoute (Anzeige) und darf keinen Request-Override erzeugen.
const reportRouteOverride = ref<AiModelRef | null>(null)

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
 * Nur ein expliziter Picker-Pick (`reportRouteOverride`) wird als Request-
 * Override für genau diese Regenerierung gesendet. Ein beim Mount aus dem
 * Kanon übernommener Anzeige-Default (`reportRoute`) erzeugt KEINEN Override:
 * ohne echte Nutzerwahl bleiben die serverseitigen Stage-/Workspace-Defaults
 * unverändert wirksam. Der Legacy-Profil-Zweig (`llm_profile_id` über
 * v3-Profil-Legacy-Picker) wurde mit Issue #834 entfernt — es gibt nur noch genau
 * eine Auswahlsenke (`ai_model_ref`).
 */
function buildModelSelection(): Pick<GenerateReportData, 'ai_model_ref'> {
  if (reportRouteOverride.value) {
    return {
      ai_model_ref: {
        provider_connection_id: reportRouteOverride.value.provider_connection_id,
        model_id: reportRouteOverride.value.model_id,
        source: reportRouteOverride.value.source ?? 'explicit',
      },
    }
  }
  return {}
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
      router.push({ name: 'Report', params: { reportId: res.data.report_id as string } })
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
      router.push({ name: 'Report', params: { reportId: res.data.report_id as string } })
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
      const st = res.data
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
        phase.value = 2; emit('update-status', 'error')
        addLog(`${t('errors.reportFailed')}: ${st.error || ''}`)
        stopPolling()
      } else { phase.value = 1 }
    }
  } catch { /* swallow */ }
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

async function loadEvidence() {
  if (!props.reportId) return
  try {
    const res = (await getReportEvidence(props.reportId)) as ApiResult
    if (!res?.success) return
    const parsed = EvidenceMapSchema.parse(res.data)
    evidenceMap.value = parsed
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
  if (props.reportId) router.push({ name: 'Interaction', params: { reportId: props.reportId } })
}

onMounted(async () => {
  // Slice 7.6c (Storage-Cut): Legacy-Route-Key einmalig defensiv entsorgen.
  localStorage.removeItem(STORAGE_REPORT_ROUTE_LEGACY)
  // Phase-1 Konsolidierung: Report-Modell aus dem Kanon initialisieren.
  effectiveModel
    .ensureLoaded()
    .then(() => { if (!reportRoute.value) reportRoute.value = effectiveModel.effectiveRef.value })
    .catch(() => { /* Kanon nicht ladbar: Backend nutzt active-config */ })
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
onUnmounted(stopPolling)
</script>

<template>
  <div class="step-panel">
    <div v-if="schemaError" class="schema-error" role="alert">
      <strong>Schema-Mismatch in {{ schemaError.where }}:</strong>
      <ul>
        <li v-for="(issue, idx) in schemaError.issues" :key="idx">{{ issue }}</li>
      </ul>
    </div>
    <div class="scroll">
      <article class="card" :class="{ 'is-active': phase === 1 }">
        <header class="card-head">
          <Kicker num="01">{{ t('step4.title') }}</Kicker>
          <div class="card-head-actions">
            <Badge :tone="reportBadgeTone" :dot="phase === 1">
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