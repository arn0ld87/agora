<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useIncrementalLogPolling } from '../composables/useIncrementalLogPolling'
import { useStickyScroll } from '../composables/useStickyScroll'
import { usePolling } from '../composables/usePolling'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { renderMarkdown } from '../utils/markdown'
import { generateReport, getAgentLog, getConsoleLog, getReport, getReportStatus, getReportEvidence } from '../api/report'
import { createSimulationBranch, getAvailableModels } from '../api/simulation'
import Btn from './ui/Btn.vue'
import Badge from './ui/Badge.vue'
import Kicker from './ui/Kicker.vue'
import StickyScrollBanner from './ui/StickyScrollBanner.vue'
import ReportBranchControls from './step4/ReportBranchControls.vue'
import ReportModelControls from './step4/ReportModelControls.vue'
import ReportOutlinePanel from './step4/ReportOutlinePanel.vue'
import ReportEvidencePanel from './step4/ReportEvidencePanel.vue'
import { useReportExports } from '../composables/useReportExports'
import {
  runtimeLlmPayloadFromStorage,
  runtimeProviderMissingApiKeyFromStorage,
} from '../composables/useRuntimeLlmOptions'
import { parseAgentEntry } from '../utils/reportAgentLog'
import { parseSourceAnchor, entryAnchorId } from '../utils/sourceAnchor'
import {
  ReportSchema,
  ReportOutlineSchema,
  EvidenceMapSchema,
  type Report,
  type ReportOutline,
  type EvidenceMap,
} from '../contracts/reportContract'

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
    ollama?: Array<{ name: string; label?: string }>
    presets?: Array<{ name: string; label?: string }>
    current_default?: string
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
  systemLogs: Array
})

const emit = defineEmits(['add-log', 'update-status'])

const phase = ref(0) // 0 idle, 1 running, 2 done
const statusMsg = ref('')
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

const STORAGE_REPORT_MODEL = 'agora.reportModel'
const STORAGE_REPORT_CUSTOM_MODEL = 'agora.reportCustomModel'
const reportModelOption = ref(localStorage.getItem(STORAGE_REPORT_MODEL) || 'default')
const customReportModel = ref(localStorage.getItem(STORAGE_REPORT_CUSTOM_MODEL) || '')
const ollamaModels = ref<Array<{ name: string; label?: string }>>([])
const presetModels = ref<Array<{ name: string; label?: string }>>([])
const defaultModel = ref('')
const isRegenerating = ref(false)

watch(reportModelOption, (val) => { localStorage.setItem(STORAGE_REPORT_MODEL, val) })
watch(customReportModel, (val) => { localStorage.setItem(STORAGE_REPORT_CUSTOM_MODEL, val) })

const modelOptions = computed(() => {
  const opts = [{ value: 'default', label: `Standard — ${defaultModel.value || '?'}` }]
  for (const p of presetModels.value) opts.push({ value: p.name, label: p.label || p.name })
  for (const m of ollamaModels.value) {
    if (presetModels.value.some(p => p.name === m.name)) continue
    opts.push({ value: m.name, label: `${m.label || m.name} (Ollama)` })
  }
  opts.push({ value: 'custom', label: 'Eigenes Modell…' })
  return opts
})

function effectiveReportModel() {
  if (reportModelOption.value === 'default') return null
  if (reportModelOption.value === 'custom') return customReportModel.value.trim() || null
  return reportModelOption.value
}

async function loadModels() {
  try {
    const res = (await getAvailableModels()) as ApiResult
    if (res?.success) {
      ollamaModels.value = (res.data?.ollama as Array<{ name: string; label?: string }>) || []
      presetModels.value = (res.data?.presets as Array<{ name: string; label?: string }>) || []
      defaultModel.value = (res.data?.current_default as string) || ''
    }
  } catch { /* swallow */ }
}

async function regenerateWithModel() {
  const simId = resolvedSimulationId.value || props.simulationId
  if (!simId) {
    addLog('simulationId fehlt — Regenerieren nicht möglich.')
    return
  }
  isRegenerating.value = true
  try {
    const payload: Record<string, unknown> = {
      simulation_id: simId,
      force_regenerate: true,
    }
    const m = effectiveReportModel()
    if (m) payload.llm_model = m
    if (runtimeProviderMissingApiKeyFromStorage()) {
      addLog(t('step2.runtimeProvider.missingKey'))
      return
    }
    const runtimeProvider = runtimeLlmPayloadFromStorage()
    if (runtimeProvider) payload.llm_provider = runtimeProvider
    addLog(`Report neu generieren${m ? ` mit ${m}` : ''}…`)
    const res = (await generateReport(payload)) as ApiResult
    if (res?.success && res.data?.report_id) {
      // Reset local UI state, then re-hydrate with the new report.
      isComplete.value = false
      phase.value = 1
      reportOutline.value = null
      generatedSections.value = {}
      currentSectionIndex.value = null
      resetAgentLogs()
      resetConsoleLogs()
      fullReport.value = null
      emit('update-status', 'processing')
      router.push({ name: 'Report', params: { reportId: res.data.report_id as string } })
      startPolling()
    } else {
      addLog(`Fehler: ${res?.error || 'unbekannt'}`)
    }
  } catch (err) {
    addLog((err as Error).message)
  } finally {
    isRegenerating.value = false
  }
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

const {
  lines: agentLogs,
  polling: agentLogPolling,
  reset: resetAgentLogs,
} = useIncrementalLogPolling({
  fetcher: (sinceLine) => props.reportId
    ? getAgentLog(props.reportId, sinceLine)
    : Promise.resolve(null),
  intervalMs: AGENT_LOG_POLLING_INTERVAL_MS,
  parseLine: parseAgentEntry,
  stickyScroll: agentSticky,
})

const {
  lines: consoleLogs,
  polling: consoleLogPolling,
  reset: resetConsoleLogs,
} = useIncrementalLogPolling({
  fetcher: (sinceLine) => props.reportId
    ? getConsoleLog(props.reportId, sinceLine)
    : Promise.resolve(null),
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
      if (st.outline) {
        try {
          reportOutline.value = ReportOutlineSchema.parse(st.outline)
        } catch (err) {
          recordSchemaError('outline', err)
        }
      }
      if (st.sections) generatedSections.value = st.sections
      currentSectionIndex.value = st.current_section_index ?? currentSectionIndex.value
      if (st.simulation_id && !resolvedSimulationId.value) {
        resolvedSimulationId.value = st.simulation_id
      }
      if (st.status === 'completed') {
        // Use the report_id the backend actually resolved (may differ if
        // the caller provided only simulation_id).
        const resolvedId = (st.report_id || props.reportId) as string
        isComplete.value = true
        phase.value = 2
        emit('update-status', 'completed')
        try {
          const full = (await getReport(resolvedId)) as ApiResult
          if (full?.success) {
            try {
              fullReport.value = ReportSchema.parse(full.data)
            } catch (err) {
              recordSchemaError('report', err)
              fullReport.value = null
            }
            await loadEvidence()
          }
        } catch { /* report not yet flushed to disk — next tick */ }
        stopPolling()
      } else if (st.status === 'failed') {
        phase.value = 2
        emit('update-status', 'error')
        addLog(`${t('errors.reportFailed')}: ${st.error || ''}`)
        stopPolling()
      } else {
        phase.value = 1
      }
    }
  } catch { /* swallow */ }
}

function startPolling() {
  void statusPolling.start()
  void agentLogPolling.start()
  void consoleLogPolling.start()
}
function stopPolling() {
  statusPolling.stop()
  agentLogPolling.stop()
  consoleLogPolling.stop()
}

const reportMarkdown = computed((): string => {
  const r = fullReport.value
  if (!r) return ''
  return r.markdown_content ?? ''
})

const reportHtml = computed(() => renderMarkdown(reportMarkdown.value))

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
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      target.classList.add('is-highlighted')
      setTimeout(() => target.classList.remove('is-highlighted'), 1500)
    }
    return
  }
  if (parsed.kind === 'web') {
    window.open(parsed.url, '_blank', 'noopener,noreferrer')
    return
  }
  if (parsed.kind === 'kg') {
    console.info('[Step4Report] KG-Anchor noch nicht aufrufbar:', parsed.payload)
  }
}

async function loadEvidence() {
  if (!props.reportId) return
  try {
    const res = (await getReportEvidence(props.reportId)) as ApiResult
    if (!res?.success) return
    const parsed = EvidenceMapSchema.parse(res.data)
    evidenceMap.value = parsed
    if (!selectedEvidenceSection.value && parsed.sections.length) {
      selectedEvidenceSection.value = parsed.sections[0].section_index
    }
  } catch (err) {
    recordSchemaError('evidence', err)
  }
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
  branch_name: string
  llm_model: string
  language: string
  max_agents: string
}) {
  const simulationId = resolvedSimulationId.value || props.simulationId
  if (!simulationId || !branchForm.branch_name.trim()) return
  branchBusy.value = true
  try {
    const overrides: Record<string, unknown> = {}
    if (branchForm.llm_model.trim()) overrides.llm_model = branchForm.llm_model.trim()
    if (branchForm.language.trim()) overrides.language = branchForm.language.trim()
    if (branchForm.max_agents !== '') overrides.max_agents = Number(branchForm.max_agents)
    const res = (await createSimulationBranch(simulationId, {
      branch_name: branchForm.branch_name.trim(),
      copy_profiles: true,
      copy_report_artifacts: false,
      overrides
    })) as ApiResult
    if (res?.success && res.data?.simulation_id) {
      router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id as string } })
    }
  } catch (e) {
    addLog((e as Error).message)
  } finally {
    branchBusy.value = false
  }
}

function goConversation() {
  if (props.reportId) router.push({ name: 'Interaction', params: { reportId: props.reportId } })
}

onMounted(async () => {
  loadModels()
  await pollStatus()
  if (!isComplete.value) {
    phase.value = 1
    startPolling()
  } else if (!fullReport.value) {
    try {
      const full = (await getReport(props.reportId!)) as ApiResult
      if (full?.success) {
        try {
          fullReport.value = ReportSchema.parse(full.data)
        } catch (err) {
          recordSchemaError('report', err)
          fullReport.value = null
        }
        await loadEvidence()
      }
    } catch { /* swallow — pollStatus will retry later */ }
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
          <Badge :variant="phase === 2 ? 'solid' : 'accent'" :dot="phase === 1">
            {{ phase === 2 ? t('common.completed') : phase === 1 ? t('common.running') : t('common.ready') }}
          </Badge>
        </header>
        <p class="card-desc">{{ t('step4.sub') }}</p>
        <p v-if="statusMsg" class="meta">{{ statusMsg }}</p>

        <ReportModelControls
          v-if="resolvedSimulationId || simulationId"
          v-model:report-model-option="reportModelOption"
          v-model:custom-report-model="customReportModel"
          :model-options="modelOptions"
          :is-regenerating="isRegenerating"
          @regenerate="regenerateWithModel"
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

      <!-- Live logs: Agent reasoning (left) + raw console (right) -->
      <article class="card" v-if="agentLogs.length || consoleLogs.length">
        <header class="card-head">
          <Kicker num="03">{{ t('step4.view.tools') }}</Kicker>
          <div class="log-meta">
            <Badge variant="ghost">{{ agentLogs.length }} agent</Badge>
            <Badge variant="ghost">{{ consoleLogs.length }} console</Badge>
          </div>
        </header>
        <div class="logs-grid">
          <div class="log-pane">
            <div class="log-pane-head">
              <span class="meta">Agent</span>
              <span class="meta">{{ agentLogs.length }}</span>
            </div>
            <div class="log-pane-scroll-wrap">
              <div ref="agentLogRef" class="log-block log-pane-body">
                <div v-if="!agentLogs.length" class="meta">Warte auf Agent-Aktivität…</div>
                <div
                  v-for="(e, i) in agentLogs"
                  :key="'a' + i"
                  :id="`agent-entry-${entryAnchorId(e)}`"
                  class="agent-entry"
                  :class="'action-' + (e.action || 'unknown')"
                >
                  <div class="agent-entry-head">
                    <span v-if="e.ts" class="agent-ts">{{ e.ts }}</span>
                    <span class="agent-title">{{ e.title }}</span>
                    <span v-if="e.elapsed" class="agent-meta">{{ e.elapsed.toFixed(1) }}s</span>
                  </div>
                  <div v-if="e.subtitle" class="agent-subtitle">{{ e.subtitle }}</div>
                  <div v-if="e.body" class="agent-body">{{ e.body.length > 600 ? e.body.slice(0, 600) + '…' : e.body }}</div>
                </div>
              </div>
              <StickyScrollBanner
                :count="agentSticky.unreadCount.value"
                @jump="agentSticky.scrollToBottom"
              />
            </div>
          </div>
          <div class="log-pane">
            <div class="log-pane-head">
              <span class="meta">Console</span>
              <span class="meta">{{ consoleLogs.length }}</span>
            </div>
            <div class="log-pane-scroll-wrap">
              <div ref="consoleLogRef" class="log-block log-pane-body">
                <div v-for="(line, i) in consoleLogs" :key="'c' + i" class="log-line console">
                  {{ line }}
                </div>
              </div>
              <StickyScrollBanner
                :count="consoleSticky.unreadCount.value"
                @jump="consoleSticky.scrollToBottom"
              />
            </div>
          </div>
        </div>
      </article>

      <!-- Rendered final report -->
      <article class="card" v-if="phase === 2 && reportHtml">
        <header class="card-head">
          <Kicker num="04" accent>Bericht</Kicker>
          <div class="log-meta">
            <Btn variant="ghost" @click="copyMarkdown">Markdown kopieren</Btn>
            <Btn variant="ghost" @click="downloadMarkdown">.md</Btn>
            <Btn variant="ghost" @click="downloadCombinedJson">.json</Btn>
            <Btn variant="ghost" @click="downloadHtml">.html</Btn>
            <Btn variant="ghost" @click="printReport">Drucken / PDF</Btn>
            <Btn v-if="evidenceSections.length" variant="ghost" @click="downloadEvidence">Evidence JSON</Btn>
          </div>
        </header>
        <div class="report-layout" :class="{ 'report-layout--stacked': !evidenceSections.length }">
          <div class="report-body markdown-body" v-html="reportHtml"></div>
          <ReportEvidencePanel
            v-if="evidenceSections.length"
            v-model:selected-section="selectedEvidenceSection"
            :sections="evidenceSections"
            @navigate="navigateToAnchor"
          />
        </div>
      </article>

      <!-- Conversation hand-off -->
      <article class="card" v-if="phase === 2">
        <header class="card-head">
          <Kicker num="05" accent>{{ t('step4.next') }}</Kicker>
        </header>
        <ReportBranchControls
          v-if="resolvedSimulationId || simulationId"
          :branch-busy="branchBusy"
          @create="createBranchFromReport"
        />
        <div class="actions">
          <Btn variant="primary" arrow @click="goConversation">{{ t('step4.next') }}</Btn>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.step-panel {
  height: 100%;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}
.card {
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card.is-active { border-color: var(--accent); }
.card-head {
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.card-desc { color: var(--fg-body); margin: 0; }

.report-body {
  max-width: 72ch;
  margin: 0 auto;
  font-family: var(--ff-serif);
  color: var(--fg);
  font-size: var(--fs-18, 17px);
  line-height: 1.75;
  padding: var(--s-4) 0;
}
.report-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(300px, 0.9fr);
  gap: var(--s-5);
}
.report-layout--stacked {
  grid-template-columns: 1fr;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-family: var(--ff-serif);
  color: var(--fg);
  line-height: 1.25;
  margin: 1.8em 0 0.4em;
  font-weight: 500;
  letter-spacing: -0.01em;
}
.markdown-body :deep(h1) { font-size: 2em; border-bottom: 1px solid var(--rule); padding-bottom: 0.3em; }
.markdown-body :deep(h2) { font-size: 1.5em; color: var(--accent); }
.markdown-body :deep(h3) { font-size: 1.2em; }
.markdown-body :deep(h4) { font-size: 1.05em; text-transform: uppercase; letter-spacing: var(--ls-mono); font-family: var(--ff-mono); color: var(--fg-muted); }
.markdown-body :deep(p) { margin: 0.9em 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0.9em 0 0.9em 1.4em; padding: 0; }
.markdown-body :deep(li) { margin: 0.35em 0; }
.markdown-body :deep(li p) { margin: 0.3em 0; }
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  margin: 1em 0;
  padding: 0.2em 1em;
  color: var(--fg-muted);
  font-style: italic;
}
.markdown-body :deep(code) {
  background: var(--bg-elevated);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: var(--ff-mono);
  font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: var(--mono-900);
  color: var(--mono-50);
  padding: 1em;
  overflow-x: auto;
  border-radius: var(--r-1);
  font-size: 12px;
  line-height: 1.5;
}
.markdown-body :deep(pre code) { background: transparent; padding: 0; color: inherit; }
.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 1em 0;
  font-family: var(--ff-sans);
  font-size: 0.95em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--rule);
  padding: 6px 10px;
  text-align: left;
}
.markdown-body :deep(th) { background: var(--bg-elevated); font-weight: 500; }
.markdown-body :deep(hr) { border: 0; border-top: 1px solid var(--rule); margin: 2em 0; }
.markdown-body :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.markdown-body :deep(strong) { font-weight: 600; color: var(--fg); }
.actions { display: flex; gap: var(--s-3); justify-content: flex-end; }

.log-meta { display: flex; gap: var(--s-2); }

.logs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
}
.log-pane {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.log-pane-scroll-wrap {
  position: relative;
}
.log-pane-head {
  display: flex;
  justify-content: space-between;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-2);
}
.log-pane-body {
  max-height: 280px;
  overflow-y: auto;
  border-radius: var(--r-1);
}
.log-block {
  max-height: 280px;
  overflow-y: auto;
}
.log-line {
  font-family: var(--ff-mono);
  font-size: 11px;
  color: var(--mono-50);
  word-wrap: break-word;
  white-space: pre-wrap;
  margin-bottom: 2px;
  line-height: 1.5;
}
.log-line.agent { color: var(--mono-50); }
.log-line.console { color: var(--mono-300); }

.agent-entry {
  padding: 6px 0;
  border-bottom: 1px dashed var(--rule-soft);
  font-family: var(--ff-mono);
  font-size: 11px;
  line-height: 1.5;
  color: var(--mono-100);
}
.agent-entry-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}
.agent-ts {
  color: var(--mono-400);
  font-size: 10px;
}
.agent-title {
  color: var(--mono-50);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.agent-meta {
  margin-left: auto;
  color: var(--mono-400);
  font-size: 10px;
}
.agent-subtitle {
  color: var(--mono-300);
  padding-left: 0;
  margin-bottom: 2px;
  word-break: break-word;
}
.agent-body {
  color: var(--mono-200);
  white-space: pre-wrap;
  word-break: break-word;
  padding: 4px 0 0 12px;
  border-left: 2px solid color-mix(in srgb, var(--accent) 35%, transparent);
  font-family: var(--ff-serif);
  font-size: 12px;
  line-height: 1.6;
}
.agent-entry.action-tool_call .agent-title { color: var(--accent); }
.agent-entry.action-tool_result .agent-title { color: var(--status-success); }
.agent-entry.action-error .agent-title { color: var(--status-error); }
.agent-entry.action-section_start .agent-title,
.agent-entry.action-section_complete .agent-title { color: var(--status-warn); }
.agent-entry.action-llm_response .agent-title { color: var(--mono-400); }

@media (max-width: 880px) {
  .logs-grid { grid-template-columns: 1fr; }
  .report-layout { grid-template-columns: 1fr; }
}

.schema-error {
  background: color-mix(in srgb, var(--status-error, #c0392b) 10%, transparent);
  border: 1px solid var(--status-error, #c0392b);
  border-radius: var(--r-1);
  padding: var(--s-4);
  margin: var(--s-4) var(--s-6) 0;
  color: var(--fg);
  font-family: var(--ff-mono);
  font-size: var(--fs-14, 13px);
}
.schema-error strong {
  display: block;
  margin-bottom: var(--s-2);
  color: var(--status-error, #c0392b);
}
.schema-error ul {
  margin: 0;
  padding-left: var(--s-4);
}
.schema-error li {
  line-height: 1.6;
}

.agent-entry.is-highlighted {
  background: var(--accent-soft);
  transition: background 0.4s ease-in-out;
}

</style>
