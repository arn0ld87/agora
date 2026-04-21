<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphPanel from '../components/GraphPanel.vue'
import Step4Report from '../components/Step4Report.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation } from '../api/simulation'
import { getReport } from '../api/report'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

defineProps({ reportId: String })

const viewMode = ref('workbench')
const currentReportId = ref(route.params.reportId)
const simulationId = ref(null)
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing')

const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1 }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0 }
  return { width: '50%', opacity: 1 }
})
const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1 }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0 }
  return { width: '50%', opacity: 1 }
})

const statusKind = computed(() => {
  if (currentStatus.value === 'error') return 'error'
  if (currentStatus.value === 'completed') return 'done'
  return 'running'
})
const statusText = computed(() => {
  if (currentStatus.value === 'error') return t('common.error')
  if (currentStatus.value === 'completed') return t('common.completed')
  return t('common.processing')
})

function addLog(msg) {
  const now = new Date()
  const time = now.toTimeString().slice(0, 8) + '.' + String(now.getMilliseconds()).padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) systemLogs.value.shift()
}
function updateStatus(s) { currentStatus.value = s }
function toggleMaximize(target) { viewMode.value = viewMode.value === target ? 'split' : target }

async function loadReportData() {
  try {
    const reportRes = await getReport(currentReportId.value)
    if (reportRes.success && reportRes.data) {
      simulationId.value = reportRes.data.simulation_id
      if (simulationId.value) {
        const simRes = await getSimulation(simulationId.value)
        if (simRes.success && simRes.data?.project_id) {
          const projRes = await getProject(simRes.data.project_id)
          if (projRes.success && projRes.data) {
            projectData.value = projRes.data
            if (projRes.data.graph_id) await loadGraph(projRes.data.graph_id)
          }
        }
      }
    }
  } catch (err) { addLog(err.message) }
}

async function loadGraph(graphId) {
  graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (res.success) graphData.value = res.data
  } finally {
    graphLoading.value = false
  }
}

function refreshGraph() {
  if (projectData.value?.graph_id) loadGraph(projectData.value.graph_id)
}

watch(() => route.params.reportId, (newId) => {
  if (newId && newId !== currentReportId.value) {
    currentReportId.value = newId
    loadReportData()
  }
}, { immediate: true })

onMounted(loadReportData)
</script>

<template>
  <div class="main-view">
    <header class="top-nav">
      <div class="brand-link" @click="router.push('/')">{{ t('brand.name') }}</div>
      <div class="view-switcher">
        <button
          v-for="mode in ['graph', 'split', 'workbench']"
          :key="mode"
          class="switch-btn"
          :class="{ active: viewMode === mode }"
          @click="viewMode = mode"
        >
          {{ { graph: 'Graph', split: 'Split', workbench: 'Workbench' }[mode] }}
        </button>
      </div>
      <div class="step-status">
        <span class="kicker-row">
          <span class="step-counter">№ 04 / 05</span>
          <span class="step-name">{{ t('process.stepper.step4') }}</span>
        </span>
        <span class="status-tag" :class="`status-${statusKind}`">
          <span class="status-dot" :class="`status-dot--${statusKind}`" />
          {{ statusText }}
        </span>
      </div>
    </header>
    <main class="content">
      <div class="panel left" :style="leftPanelStyle">
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="4"
          :isSimulating="false"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>
      <div class="panel right" :style="rightPanelStyle">
        <Step4Report
          :reportId="currentReportId"
          :simulationId="simulationId"
          :systemLogs="systemLogs"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>
    </main>
  </div>
</template>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--paper-0);
  overflow: hidden;
}
.top-nav {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--s-7);
  padding: var(--s-4) var(--s-6);
  border-bottom: 1px solid var(--rule-strong);
  background: var(--paper-0);
  z-index: 10;
}
.brand-link {
  font-family: var(--ff-serif);
  font-weight: 500;
  font-size: 22px;
  letter-spacing: -0.02em;
  cursor: pointer;
  color: var(--ink-0);
}
.brand-link:hover { color: var(--accent); }
.view-switcher {
  display: inline-flex;
  justify-self: center;
  gap: var(--s-2);
  padding: 4px;
  background: var(--paper-1);
  border-radius: var(--r-1);
}
.switch-btn {
  border: 0;
  background: transparent;
  padding: 6px 14px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  border-radius: var(--r-1);
  cursor: pointer;
}
.switch-btn:hover { color: var(--ink-0); }
.switch-btn.active { background: var(--paper-0); color: var(--ink-0); border: 1px solid var(--rule); }
.step-status { display: inline-flex; align-items: center; gap: var(--s-5); }
.kicker-row { display: inline-flex; align-items: baseline; gap: var(--s-3); }
.step-counter {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.step-name {
  font-family: var(--ff-serif);
  font-size: var(--fs-20);
  color: var(--ink-0);
}
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.status-tag.status-error { color: #b00020; }
.status-tag.status-done { color: var(--ink-0); }
.status-tag.status-running { color: var(--accent); }
.content { flex: 1; display: flex; overflow: hidden; }
.panel { height: 100%; overflow: hidden; transition: width 350ms cubic-bezier(0.2, 0.7, 0.2, 1), opacity 200ms ease; }
.panel.left { border-right: 1px solid var(--rule); }
</style>
