<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphPanel from '../components/GraphPanel.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import WorkspaceBrandLink from '../layouts/WorkspaceBrandLink.vue'
import WorkspaceHeader from '../layouts/WorkspaceHeader.vue'
import WorkspaceLayout from '../layouts/WorkspaceLayout.vue'
import WorkspaceModeSwitch from '../layouts/WorkspaceModeSwitch.vue'
import WorkspaceSplit from '../layouts/WorkspaceSplit.vue'
import WorkspaceStepStatus from '../layouts/WorkspaceStepStatus.vue'
import { getProject, getGraphData } from '../api/graph'
import { createSimulationBranch, getSimulation, stopSimulation, getEnvStatus, closeSimulationEnv } from '../api/simulation'
import { useSystemLog } from '../composables/useSystemLog'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

defineProps({ simulationId: String })

const viewMode = ref('split')
const workspaceModes = [
  { value: 'graph', label: 'Graph' },
  { value: 'split', label: 'Split' },
  { value: 'workbench', label: 'Workbench' },
]
const currentSimulationId = ref(route.params.simulationId)
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const { systemLogs, addLog } = useSystemLog({ cap: 100 })
const currentStatus = ref('processing')
const showBranchPanel = ref(false)
const branchBusy = ref(false)
const branchForm = ref({
  branch_name: '',
  llm_model: '',
  language: '',
  max_agents: ''
})

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
  if (currentStatus.value === 'completed') return t('common.ready')
  return t('common.preparing')
})

function updateStatus(s) { currentStatus.value = s }
function toggleMaximize(target) {
  viewMode.value = viewMode.value === target ? 'split' : target
}

function handleGoBack() {
  if (projectData.value?.project_id) {
    router.push({ name: 'Process', params: { projectId: projectData.value.project_id } })
  } else {
    router.push('/')
  }
}

function handleNextStep(params = {}) {
  const routeParams = {
    name: 'SimulationRun',
    params: { simulationId: currentSimulationId.value }
  }
  if (params.maxRounds) routeParams.query = { maxRounds: params.maxRounds }
  router.push(routeParams)
}

async function handleCreateBranch() {
  if (!currentSimulationId.value || !branchForm.value.branch_name.trim()) return
  branchBusy.value = true
  try {
    const overrides = {}
    if (branchForm.value.llm_model.trim()) overrides.llm_model = branchForm.value.llm_model.trim()
    if (branchForm.value.language.trim()) overrides.language = branchForm.value.language.trim()
    if (branchForm.value.max_agents !== '') overrides.max_agents = Number(branchForm.value.max_agents)
    const res = await createSimulationBranch(currentSimulationId.value, {
      branch_name: branchForm.value.branch_name.trim(),
      copy_profiles: true,
      copy_report_artifacts: false,
      overrides
    })
    if (res?.success && res.data?.simulation_id) {
      router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id } })
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    branchBusy.value = false
  }
}

async function checkAndStopRunningSimulation() {
  if (!currentSimulationId.value) return
  try {
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      try {
        const closeRes = await closeSimulationEnv({ simulation_id: currentSimulationId.value, timeout: 10 })
        if (!closeRes.success) await forceStopSimulation()
      } catch {
        await forceStopSimulation()
      }
    } else {
      const simRes = await getSimulation(currentSimulationId.value)
      if (simRes.success && simRes.data?.status === 'running') await forceStopSimulation()
    }
  } catch (err) {
    console.warn('Status check failed:', err)
  }
}

async function forceStopSimulation() {
  try {
    await stopSimulation({ simulation_id: currentSimulationId.value })
  } catch {
    // Best-effort stop: the caller already handles degraded states.
  }
}

async function loadSimulationData() {
  try {
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data?.project_id) {
      const projRes = await getProject(simRes.data.project_id)
      if (projRes.success && projRes.data) {
        projectData.value = projRes.data
        if (projRes.data.graph_id) await loadGraph(projRes.data.graph_id)
      }
    }
  } catch (err) {
    addLog(err.message)
  }
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

onMounted(async () => {
  addLog('SimulationView init')
  await checkAndStopRunningSimulation()
  loadSimulationData()
})
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
            step-counter="№ 02 / 05"
            :step-name="t('process.stepper.step2')"
            :status-kind="statusKind"
            :status-text="statusText"
          >
            <button class="branch-btn" @click="showBranchPanel = !showBranchPanel">Create Branch</button>
          </WorkspaceStepStatus>
        </template>
      </WorkspaceHeader>
    </template>

    <div v-if="showBranchPanel" class="branch-panel">
      <input v-model="branchForm.branch_name" type="text" placeholder="Branch name" />
      <input v-model="branchForm.llm_model" type="text" placeholder="LLM model override" />
      <input v-model="branchForm.language" type="text" placeholder="language" />
      <input v-model="branchForm.max_agents" type="number" min="1" placeholder="max agents" />
      <button class="branch-btn" :disabled="branchBusy" @click="handleCreateBranch">Create</button>
    </div>

    <WorkspaceSplit :left-style="leftPanelStyle" :right-style="rightPanelStyle">
      <template #left>
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="2"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </template>

      <template #right>
        <Step2EnvSetup
          :simulationId="currentSimulationId"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </template>
    </WorkspaceSplit>
  </WorkspaceLayout>
</template>

<style scoped>
.branch-btn {
  border: 1px solid var(--rule);
  background: var(--paper-0);
  color: var(--ink-0);
  padding: 8px 12px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  cursor: pointer;
}
.branch-panel {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--s-3);
  padding: var(--s-4) var(--s-6);
  border-bottom: 1px solid var(--rule);
  background: var(--paper-1);
}
.branch-panel input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--rule);
  background: var(--paper-0);
  color: var(--ink-0);
  font-family: var(--ff-sans);
}
@media (max-width: 880px) {
  .branch-panel { grid-template-columns: 1fr; }
}
</style>
