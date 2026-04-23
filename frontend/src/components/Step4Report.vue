<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { usePolling } from '../composables/usePolling'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import { generateReport, getAgentLog, getConsoleLog, getReport, getReportStatus, getReportEvidence } from '../api/report'
import { createSimulationBranch, getAvailableModels } from '../api/simulation'
import Btn from './ui/Btn.vue'
import Badge from './ui/Badge.vue'
import Kicker from './ui/Kicker.vue'
import Select from './ui/Select.vue'

marked.setOptions({ gfm: true, breaks: false, mangle: false, headerIds: false })

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
const reportOutline = ref(null)
const generatedSections = ref({})
const currentSectionIndex = ref(null)
const agentLogs = ref([])           // structured entries (parsed)
const consoleLogs = ref([])
const agentLogLine = ref(0)
const consoleLogLine = ref(0)
const isComplete = ref(false)
const fullReport = ref(null)
const collapsedSections = ref(new Set())
const agentLogRef = ref(null)
const consoleLogRef = ref(null)
const evidenceMap = ref(null)
const selectedEvidenceSection = ref(null)
const branchBusy = ref(false)
const branchForm = ref({
  branch_name: '',
  llm_model: '',
  language: '',
  max_agents: ''
})
// Resolved from /generate/status when only reportId was known on mount.
const resolvedSimulationId = ref(props.simulationId || null)

// ----- Per-report model override (falls back to .env LLM_MODEL_NAME) -----
const STORAGE_REPORT_MODEL = 'agora.reportModel'
const reportModelOption = ref(localStorage.getItem(STORAGE_REPORT_MODEL) || 'default')
const customReportModel = ref('')
const ollamaModels = ref([])
const presetModels = ref([])
const defaultModel = ref('')
const isRegenerating = ref(false)

watch(reportModelOption, (val) => { localStorage.setItem(STORAGE_REPORT_MODEL, val) })

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
    const res = await getAvailableModels()
    if (res?.success) {
      ollamaModels.value = res.data?.ollama || []
      presetModels.value = res.data?.presets || []
      defaultModel.value = res.data?.current_default || ''
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
    const payload = {
      simulation_id: simId,
      force_regenerate: true,
    }
    const m = effectiveReportModel()
    if (m) payload.llm_model = m
    addLog(`Report neu generieren${m ? ` mit ${m}` : ''}…`)
    const res = await generateReport(payload)
    if (res?.success && res.data?.report_id) {
      // Reset local UI state, then re-hydrate with the new report.
      isComplete.value = false
      phase.value = 1
      reportOutline.value = null
      generatedSections.value = {}
      currentSectionIndex.value = null
      agentLogs.value = []
      consoleLogs.value = []
      agentLogLine.value = 0
      consoleLogLine.value = 0
      fullReport.value = null
      emit('update-status', 'processing')
      router.push({ name: 'Report', params: { reportId: res.data.report_id } })
      startPolling()
    } else {
      addLog(`Fehler: ${res?.error || 'unbekannt'}`)
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isRegenerating.value = false
  }
}

function addLog(msg) { emit('add-log', msg) }

const statusPolling = usePolling(pollStatus, 2500)
const agentLogPolling = usePolling(pollAgentLog, 1500)
const consoleLogPolling = usePolling(pollConsoleLog, 2000)

async function pollStatus() {
  if (!props.reportId && !props.simulationId) return
  try {
    const res = await getReportStatus({
      simulationId: resolvedSimulationId.value || props.simulationId,
      reportId: props.reportId,
    })
    if (res?.success && res.data) {
      const st = res.data
      statusMsg.value = st.message || ''
      reportOutline.value = st.outline || reportOutline.value
      if (st.sections) generatedSections.value = st.sections
      currentSectionIndex.value = st.current_section_index ?? currentSectionIndex.value
      if (st.simulation_id && !resolvedSimulationId.value) {
        resolvedSimulationId.value = st.simulation_id
      }
      if (st.status === 'completed') {
        // Use the report_id the backend actually resolved (may differ if
        // the caller provided only simulation_id).
        const resolvedId = st.report_id || props.reportId
        isComplete.value = true
        phase.value = 2
        emit('update-status', 'completed')
        try {
          const full = await getReport(resolvedId)
          if (full?.success) {
            fullReport.value = full.data
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

function parseAgentEntry(raw) {
  // Each backend line is a JSON object (or JSON-encoded string). Parse defensively.
  let obj = null
  if (typeof raw === 'string') {
    try { obj = JSON.parse(raw) } catch { obj = { action: 'raw', message: raw } }
  } else if (raw && typeof raw === 'object') {
    obj = raw
  } else {
    return null
  }
  const ts = obj.timestamp ? String(obj.timestamp).slice(11, 19) : ''
  const stage = obj.stage || ''
  const action = obj.action || ''
  const d = obj.details || {}
  let title = action.replace(/_/g, ' ')
  let subtitle = ''
  let body = ''

  if (action === 'tool_call') {
    title = `TOOL → ${obj.tool_name || d.tool_name || '?'}`
    const params = d.parameters || {}
    subtitle = Object.entries(params).map(([k, v]) => {
      const str = typeof v === 'string' ? v : JSON.stringify(v)
      return `${k}=${str.length > 80 ? str.slice(0, 80) + '…' : str}`
    }).join('  ')
  } else if (action === 'tool_result') {
    title = `← ${obj.tool_name || d.tool_name || '?'}`
    subtitle = `${d.result_length || 0} chars`
  } else if (action === 'llm_response') {
    title = 'LLM'
    subtitle = `iter ${d.iteration ?? ''} · tool_calls=${d.has_tool_calls} · final=${d.has_final_answer}`
    body = d.response || ''
  } else if (action === 'section_start') {
    title = `▶ Section ${obj.section_index ?? ''}: ${obj.section_title || d.message || ''}`
  } else if (action === 'section_complete') {
    title = `✓ Section ${obj.section_index ?? ''}`
    subtitle = d.message || ''
  } else if (action === 'planning_complete') {
    title = 'PLAN'
    const outline = d.outline?.sections || []
    subtitle = `${outline.length} sections`
    body = d.summary || ''
  } else if (action === 'error') {
    title = '⚠ ERROR'
    subtitle = d.message || d.error || ''
  }
  return {
    ts,
    stage,
    action,
    title,
    subtitle,
    body,
    elapsed: obj.elapsed_seconds,
  }
}

async function pollAgentLog() {
  if (!props.reportId) return
  try {
    const res = await getAgentLog(props.reportId, agentLogLine.value)
    const payload = res?.data
    const lines = payload?.lines || payload?.logs
    if (res?.success && Array.isArray(lines)) {
      for (const line of lines) {
        const entry = parseAgentEntry(line)
        if (entry) agentLogs.value.push(entry)
      }
      agentLogLine.value = payload.next_line ?? payload.total_lines ?? agentLogLine.value
      nextTick(() => { if (agentLogRef.value) agentLogRef.value.scrollTop = agentLogRef.value.scrollHeight })
    }
  } catch { /* swallow */ }
}

async function pollConsoleLog() {
  if (!props.reportId) return
  try {
    const res = await getConsoleLog(props.reportId, consoleLogLine.value)
    const payload = res?.data
    const lines = payload?.lines || payload?.logs
    if (res?.success && Array.isArray(lines)) {
      for (const line of lines) consoleLogs.value.push(line)
      consoleLogLine.value = payload.next_line ?? payload.total_lines ?? consoleLogLine.value
      nextTick(() => { if (consoleLogRef.value) consoleLogRef.value.scrollTop = consoleLogRef.value.scrollHeight })
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

function toggleSection(i) {
  const next = new Set(collapsedSections.value)
  next.has(i) ? next.delete(i) : next.add(i)
  collapsedSections.value = next
}

function renderMarkdown(text) {
  if (!text) return ''
  try { return marked.parse(text) } catch { return text }
}

const reportMarkdown = computed(() => {
  const r = fullReport.value
  if (!r) return ''
  if (typeof r.full_text === 'string' && r.full_text.trim()) return r.full_text
  if (typeof r.markdown === 'string' && r.markdown.trim()) return r.markdown
  if (typeof r.markdown_content === 'string' && r.markdown_content.trim()) return r.markdown_content
  if (Array.isArray(r.sections) && r.sections.length) {
    return r.sections.map((s) => `## ${s.title || ''}\n\n${s.content || ''}`).join('\n\n')
  }
  return ''
})

const reportHtml = computed(() => renderMarkdown(reportMarkdown.value))

const sectionHtml = computed(() => {
  const map = {}
  for (const [k, v] of Object.entries(generatedSections.value || {})) {
    const text = (v && typeof v === 'object') ? (v.content || '') : (v || '')
    map[k] = renderMarkdown(text)
  }
  return map
})

const evidenceSections = computed(() => evidenceMap.value?.sections || [])
const activeEvidenceSection = computed(() => {
  return evidenceSections.value.find((section) => section.section_index === selectedEvidenceSection.value) || null
})

async function loadEvidence() {
  if (!props.reportId) return
  try {
    const res = await getReportEvidence(props.reportId)
    if (res?.success) {
      evidenceMap.value = res.data
      if (!selectedEvidenceSection.value && Array.isArray(res.data?.sections) && res.data.sections.length) {
        selectedEvidenceSection.value = res.data.sections[0].section_index
      }
    }
  } catch { /* optional */ }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 500)
}

function downloadMarkdown() {
  const md = reportMarkdown.value
  if (!md) return
  triggerDownload(
    new Blob([md], { type: 'text/markdown;charset=utf-8' }),
    `agora-report-${props.reportId}.md`
  )
}

function buildStandaloneHtml(title, bodyHtml) {
  return `<!doctype html>
<html lang="de"><head><meta charset="utf-8" />
<title>${title}</title>
<style>
  body { font-family: Georgia, 'Iowan Old Style', serif; max-width: 740px; margin: 48px auto; padding: 0 24px; color: #111; line-height: 1.6; font-size: 16px; }
  h1,h2,h3,h4 { font-family: Georgia, serif; line-height: 1.25; margin: 2em 0 0.4em; }
  h1 { font-size: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
  h2 { font-size: 1.5em; }
  h3 { font-size: 1.2em; }
  p { margin: 0.8em 0; }
  ul, ol { margin: 0.8em 0 0.8em 1.4em; }
  li { margin: 0.3em 0; }
  blockquote { border-left: 3px solid #e2681a; margin: 1em 0; padding: 0.2em 1em; color: #555; font-style: italic; }
  code { background: #f3f3f3; padding: 2px 4px; border-radius: 3px; font-size: 0.92em; }
  pre { background: #1a1a1a; color: #eee; padding: 1em; overflow: auto; border-radius: 4px; }
  pre code { background: transparent; color: inherit; padding: 0; }
  table { border-collapse: collapse; margin: 1em 0; }
  th, td { border: 1px solid #ccc; padding: 6px 10px; }
  hr { border: 0; border-top: 1px solid #ccc; margin: 2em 0; }
  @media print { body { margin: 0; padding: 24px; } }
</style>
</head>
<body>
<h1>${title}</h1>
${bodyHtml}
</body></html>`
}

function downloadHtml() {
  const html = buildStandaloneHtml(
    `Agora-Report · ${props.reportId || ''}`,
    reportHtml.value
  )
  triggerDownload(
    new Blob([html], { type: 'text/html;charset=utf-8' }),
    `agora-report-${props.reportId}.html`
  )
}

function printReport() {
  const html = buildStandaloneHtml(
    `Agora-Report · ${props.reportId || ''}`,
    reportHtml.value
  )
  const w = window.open('', '_blank')
  if (!w) {
    addLog('Popup blockiert — bitte Popups erlauben.')
    return
  }
  w.document.open()
  w.document.write(html)
  w.document.close()
  // Give the browser a tick to render, then trigger print.
  w.addEventListener('load', () => {
    setTimeout(() => w.print(), 200)
  })
}

async function copyMarkdown() {
  const md = reportMarkdown.value
  if (!md) return
  try {
    await navigator.clipboard.writeText(md)
    addLog('Markdown in Zwischenablage kopiert.')
  } catch (e) {
    addLog('Kopieren fehlgeschlagen: ' + e.message)
  }
}

function downloadEvidence() {
  if (!evidenceMap.value) return
  triggerDownload(
    new Blob([JSON.stringify(evidenceMap.value, null, 2)], { type: 'application/json;charset=utf-8' }),
    `agora-report-${props.reportId}-evidence.json`
  )
}

async function createBranchFromReport() {
  const simulationId = resolvedSimulationId.value || props.simulationId
  if (!simulationId || !branchForm.value.branch_name.trim()) return
  branchBusy.value = true
  try {
    const overrides = {}
    if (branchForm.value.llm_model.trim()) overrides.llm_model = branchForm.value.llm_model.trim()
    if (branchForm.value.language.trim()) overrides.language = branchForm.value.language.trim()
    if (branchForm.value.max_agents !== '') overrides.max_agents = Number(branchForm.value.max_agents)
    const res = await createSimulationBranch(simulationId, {
      branch_name: branchForm.value.branch_name.trim(),
      copy_profiles: true,
      copy_report_artifacts: false,
      overrides
    })
    if (res?.success && res.data?.simulation_id) {
      router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id } })
    }
  } catch (e) {
    addLog(e.message)
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
      const full = await getReport(props.reportId)
      if (full?.success) {
        fullReport.value = full.data
        await loadEvidence()
      }
    } catch { /* swallow — pollStatus will retry later */ }
  }
})
onUnmounted(stopPolling)
</script>

<template>
  <div class="step-panel">
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

        <!-- Per-report model override + regenerate -->
        <div class="model-row" v-if="resolvedSimulationId || simulationId">
          <div class="model-cell">
            <Select
              v-model="reportModelOption"
              label="Modell für Report"
              :options="modelOptions"
            />
          </div>
          <div class="model-cell" v-if="reportModelOption === 'custom'">
            <label class="field-label">Eigenes Modell</label>
            <input
              v-model="customReportModel"
              class="model-input"
              type="text"
              placeholder="z. B. deepseek-v3.2:cloud"
            />
          </div>
          <Btn
            variant="ghost"
            :loading="isRegenerating"
            :disabled="isRegenerating"
            @click="regenerateWithModel"
          >Neu generieren</Btn>
        </div>
      </article>

      <!-- Outline + sections -->
      <article class="card" v-if="reportOutline?.sections">
        <header class="card-head">
          <Kicker num="02">{{ t('step4.view.sections') }}</Kicker>
          <Badge variant="ghost">{{ Object.keys(generatedSections).length }} / {{ reportOutline.sections.length }}</Badge>
        </header>
        <ol class="outline">
          <li
            v-for="(sec, i) in reportOutline.sections"
            :key="i"
            :class="{ 'is-current': currentSectionIndex === i }"
          >
            <header class="outline-head" @click="toggleSection(i)">
              <span class="outline-num">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="outline-title">{{ sec.title }}</span>
              <Badge :variant="generatedSections[i + 1] ? 'solid' : 'ghost'">
                {{ generatedSections[i + 1] ? '✓' : (currentSectionIndex === i ? '…' : '—') }}
              </Badge>
            </header>
            <div
              class="outline-body"
              v-if="generatedSections[i + 1] && !collapsedSections.has(i)"
            >
              <div class="section-content markdown-body" v-html="sectionHtml[i + 1] || ''"></div>
            </div>
          </li>
        </ol>
      </article>

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
            <div ref="agentLogRef" class="log-block log-pane-body">
              <div v-if="!agentLogs.length" class="meta">Warte auf Agent-Aktivität…</div>
              <div v-for="(e, i) in agentLogs" :key="'a' + i" class="agent-entry" :class="'action-' + (e.action || 'unknown')">
                <div class="agent-entry-head">
                  <span v-if="e.ts" class="agent-ts">{{ e.ts }}</span>
                  <span class="agent-title">{{ e.title }}</span>
                  <span v-if="e.elapsed" class="agent-meta">{{ e.elapsed.toFixed(1) }}s</span>
                </div>
                <div v-if="e.subtitle" class="agent-subtitle">{{ e.subtitle }}</div>
                <div v-if="e.body" class="agent-body">{{ e.body.length > 600 ? e.body.slice(0, 600) + '…' : e.body }}</div>
              </div>
            </div>
          </div>
          <div class="log-pane">
            <div class="log-pane-head">
              <span class="meta">Console</span>
              <span class="meta">{{ consoleLogs.length }}</span>
            </div>
            <div ref="consoleLogRef" class="log-block log-pane-body">
              <div v-for="(line, i) in consoleLogs" :key="'c' + i" class="log-line console">
                {{ line }}
              </div>
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
            <Btn variant="ghost" @click="downloadHtml">.html</Btn>
            <Btn variant="ghost" @click="printReport">Drucken / PDF</Btn>
            <Btn v-if="evidenceSections.length" variant="ghost" @click="downloadEvidence">Evidence JSON</Btn>
          </div>
        </header>
        <div class="report-layout" :class="{ 'report-layout--stacked': !evidenceSections.length }">
          <div class="report-body markdown-body" v-html="reportHtml"></div>
          <aside v-if="evidenceSections.length" class="evidence-panel">
            <div class="evidence-head">
              <strong>Evidence Inspector</strong>
              <span>{{ evidenceSections.length }} sections</span>
            </div>
            <div class="evidence-sections">
              <button
                v-for="section in evidenceSections"
                :key="section.section_index"
                class="evidence-tab"
                :class="{ active: selectedEvidenceSection === section.section_index }"
                @click="selectedEvidenceSection = section.section_index"
              >
                {{ section.section_index }} · {{ section.section_title }}
              </button>
            </div>
            <div v-if="activeEvidenceSection" class="evidence-body">
              <p class="meta">{{ activeEvidenceSection.section_summary }}</p>
              <article v-for="claim in activeEvidenceSection.claims" :key="claim.claim_id" class="claim-card">
                <header>
                  <strong>{{ claim.claim_id }}</strong>
                  <Badge :variant="claim.confidence === 'low' ? 'ghost' : claim.confidence === 'medium' ? 'accent' : 'solid'">
                    {{ claim.confidence }}
                  </Badge>
                </header>
                <p>{{ claim.claim_text }}</p>
                <div class="evidence-items">
                  <div v-for="(item, idx) in claim.evidence_items" :key="`${claim.claim_id}-${idx}`" class="evidence-item">
                    <Badge variant="ghost">{{ item.type }}</Badge>
                    <span>{{ item.snippet }}</span>
                  </div>
                </div>
              </article>
            </div>
          </aside>
        </div>
      </article>

      <!-- Conversation hand-off -->
      <article class="card" v-if="phase === 2">
        <header class="card-head">
          <Kicker num="05" accent>{{ t('step4.next') }}</Kicker>
        </header>
        <div class="branch-controls" v-if="resolvedSimulationId || simulationId">
          <input v-model="branchForm.branch_name" class="model-input" type="text" placeholder="Branch name" />
          <input v-model="branchForm.llm_model" class="model-input" type="text" placeholder="LLM model override" />
          <input v-model="branchForm.language" class="model-input" type="text" placeholder="language" />
          <input v-model="branchForm.max_agents" class="model-input" type="number" min="1" placeholder="max agents" />
          <Btn variant="ghost" :loading="branchBusy" :disabled="branchBusy" @click="createBranchFromReport">Create Branch</Btn>
        </div>
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
  background: var(--paper-0);
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
  background: var(--paper-0);
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

.outline {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
}
.outline li {
  border-top: 1px solid var(--rule);
  padding: var(--s-3) 0;
}
.outline li:last-child { border-bottom: 1px solid var(--rule); }
.outline-head {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  gap: var(--s-3);
  align-items: baseline;
  cursor: pointer;
}
.outline-num {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
}
.outline-title {
  font-family: var(--ff-serif);
  font-size: var(--fs-20);
  color: var(--ink-0);
}
.outline-body {
  margin-top: var(--s-3);
  padding-left: 32px;
}
.section-content {
  font-family: var(--ff-serif);
  font-size: var(--fs-16);
  line-height: 1.7;
  color: var(--ink-0);
  margin: 0;
}

.report-body {
  max-width: 72ch;
  margin: 0 auto;
  font-family: var(--ff-serif);
  color: var(--ink-0);
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
.evidence-panel {
  border-left: 1px solid var(--rule);
  padding-left: var(--s-4);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.evidence-head {
  display: flex;
  justify-content: space-between;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.evidence-sections {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.evidence-tab {
  border: 1px solid var(--rule);
  background: var(--paper-0);
  color: var(--ink-0);
  text-align: left;
  padding: 10px 12px;
  cursor: pointer;
}
.evidence-tab.active { border-color: var(--accent); background: var(--paper-1); }
.claim-card {
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.claim-card header {
  display: flex;
  justify-content: space-between;
  gap: var(--s-3);
  align-items: center;
}
.evidence-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: var(--s-3);
}
.evidence-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: var(--paper-1);
  border: 1px solid var(--rule);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-family: var(--ff-serif);
  color: var(--ink-0);
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
  background: var(--paper-1);
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
.markdown-body :deep(th) { background: var(--paper-1); font-weight: 500; }
.markdown-body :deep(hr) { border: 0; border-top: 1px solid var(--rule); margin: 2em 0; }
.markdown-body :deep(a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.markdown-body :deep(strong) { font-weight: 600; color: var(--ink-0); }
.outline li.is-current .outline-title { color: var(--accent); }

.actions { display: flex; gap: var(--s-3); justify-content: flex-end; }
.branch-controls {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--s-3);
}

.model-row {
  display: grid;
  grid-template-columns: 2fr 2fr auto;
  gap: var(--s-3);
  align-items: end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.model-cell { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.field-label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.model-input {
  background: var(--paper-1);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  color: var(--ink-0);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 8px 10px;
  outline: none;
}
.model-input:focus { border-color: var(--accent); }
@media (max-width: 720px) {
  .model-row { grid-template-columns: 1fr; }
  .branch-controls { grid-template-columns: 1fr; }
}

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
  border-bottom: 1px dashed rgba(255,255,255,0.08);
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
  border-left: 2px solid rgba(226,104,26,0.35);
  font-family: var(--ff-serif);
  font-size: 12px;
  line-height: 1.6;
}
.agent-entry.action-tool_call .agent-title { color: var(--accent); }
.agent-entry.action-tool_result .agent-title { color: #7cdc8e; }
.agent-entry.action-error .agent-title { color: #ff8a8a; }
.agent-entry.action-section_start .agent-title,
.agent-entry.action-section_complete .agent-title { color: #f0c14b; }
.agent-entry.action-llm_response .agent-title { color: var(--mono-400); }

@media (max-width: 880px) {
  .logs-grid { grid-template-columns: 1fr; }
  .report-layout { grid-template-columns: 1fr; }
  .evidence-panel {
    border-left: 0;
    border-top: 1px solid var(--rule);
    padding-left: 0;
    padding-top: var(--s-4);
  }
}
</style>
