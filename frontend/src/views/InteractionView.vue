<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphPanel from '../components/GraphPanel.vue'
import Step5Interaction from '../components/Step5Interaction.vue'
import WorkspaceBrandLink from '../layouts/WorkspaceBrandLink.vue'
import WorkspaceHeader from '../layouts/WorkspaceHeader.vue'
import WorkspaceLayout from '../layouts/WorkspaceLayout.vue'
import WorkspaceModeSwitch from '../layouts/WorkspaceModeSwitch.vue'
import WorkspaceSplit from '../layouts/WorkspaceSplit.vue'
import WorkspaceStepStatus from '../layouts/WorkspaceStepStatus.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation } from '../api/simulation'
import { getReport } from '../api/report'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

defineProps({ reportId: String })

const viewMode = ref('workbench')
const workspaceModes = [
  { value: 'graph', label: 'Graph' },
  { value: 'split', label: 'Split' },
  { value: 'workbench', label: 'Workbench' },
]
const currentReportId = ref(route.params.reportId)
const simulationId = ref(null)
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('completed')

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
  if (currentStatus.value === 'processing') return 'running'
  return 'done'
})
const statusText = computed(() => {
  if (currentStatus.value === 'error') return t('common.error')
  if (currentStatus.value === 'processing') return t('common.thinking')
  return t('common.ready')
})

function addLog(msg) {
  const now = new Date()
  const time = now.toTimeString().slice(0, 8) + '.' + String(now.getMilliseconds()).padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) systemLogs.value.shift()
}
function updateStatus(s) { currentStatus.value = s }
function toggleMaximize(target) { viewMode.value = viewMode.value === target ? 'split' : target }

async function loadData() {
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

function refreshGraph() { if (projectData.value?.graph_id) loadGraph(projectData.value.graph_id) }

watch(() => route.params.reportId, (n) => {
  if (n && n !== currentReportId.value) { currentReportId.value = n; loadData() }
}, { immediate: true })

onMounted(loadData)
</script>

<template>
  <WorkspaceLayout>
    <template #header>
      <WorkspaceHeader>
        <template #brand>
          <WorkspaceBrandLink @navigate-home="router.push('/')">
            {{ t('brand.name') }}
          </WorkspaceBrandLink>
        </template>

        <template #center>
          <WorkspaceModeSwitch
            :current-mode="viewMode"
            :modes="workspaceModes"
            @update:mode="viewMode = $event"
          />
        </template>

        <template #status>
          <WorkspaceStepStatus
            step-counter="№ 05 / 05"
            :step-name="t('process.stepper.step5')"
            :status-kind="statusKind"
            :status-text="statusText"
          />
        </template>
      </WorkspaceHeader>
    </template>

    <WorkspaceSplit :left-style="leftPanelStyle" :right-style="rightPanelStyle">
      <template #left>
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="5"
          :isSimulating="false"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </template>

      <template #right>
        <Step5Interaction
          :reportId="currentReportId"
          :simulationId="simulationId"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </template>
    </WorkspaceSplit>
  </WorkspaceLayout>
</template>

<style scoped>
</style>
