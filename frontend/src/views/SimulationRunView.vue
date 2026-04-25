<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphPanel from '../components/GraphPanel.vue'
import Step3Simulation from '../components/Step3Simulation.vue'
import WorkspaceBrandLink from '../layouts/WorkspaceBrandLink.vue'
import WorkspaceHeader from '../layouts/WorkspaceHeader.vue'
import WorkspaceLayout from '../layouts/WorkspaceLayout.vue'
import WorkspaceModeSwitch from '../layouts/WorkspaceModeSwitch.vue'
import WorkspaceSplit from '../layouts/WorkspaceSplit.vue'
import WorkspaceStepStatus from '../layouts/WorkspaceStepStatus.vue'
import { getProject, getGraphData } from '../api/graph'
import {
  getSimulation,
  getSimulationConfig,
  stopSimulation,
  closeSimulationEnv,
  getEnvStatus,
  getRunStatus,
  pauseSimulation,
  resumeSimulation
} from '../api/simulation'
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
const maxRounds = ref(route.query.maxRounds ? parseInt(route.query.maxRounds) : null)
const minutesPerRound = ref(30)
const projectData = ref(null)
const graphData = ref(null)
const graphLoading = ref(false)
const { systemLogs, addLog } = useSystemLog({ cap: 200 })
const currentStatus = ref('processing')
const isPaused = ref(false)
const currentRound = ref(0)
const totalRounds = ref(0)
const isPauseToggling = ref(false)
let statusTimer = null

async function pollGlobalStatus() {
  if (!currentSimulationId.value) return
  try {
    const res = await getRunStatus(currentSimulationId.value)
    if (res?.success && res.data) {
      isPaused.value = !!res.data.paused
      currentRound.value = res.data.current_round || 0
      totalRounds.value = res.data.total_rounds || 0
      const rs = res.data.runner_status
      if (rs === 'completed') currentStatus.value = 'completed'
      else if (rs === 'failed') currentStatus.value = 'error'
    }
  } catch { /* swallow */ }
}

async function togglePause() {
  if (!currentSimulationId.value || isPauseToggling.value) return
  isPauseToggling.value = true
  try {
    if (isPaused.value) {
      const res = await resumeSimulation(currentSimulationId.value)
      if (res?.success) { isPaused.value = false; addLog(t('step3.controls.resume')) }
    } else {
      const res = await pauseSimulation(currentSimulationId.value)
      if (res?.success) { isPaused.value = true; addLog(t('step3.controls.pauseHint')) }
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isPauseToggling.value = false
  }
}

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
  if (isPaused.value) return 'paused'
  return 'running'
})
const statusText = computed(() => {
  if (currentStatus.value === 'error') return t('common.error')
  if (currentStatus.value === 'completed') return t('common.completed')
  if (isPaused.value) {
    return t('step3.status.paused', {
      current: currentRound.value || 0,
      total: totalRounds.value || maxRounds.value || '?'
    })
  }
  return t('step3.status.running', {
    current: currentRound.value || 0,
    total: totalRounds.value || maxRounds.value || '?'
  })
})
const isSimulating = computed(() => currentStatus.value === 'processing')

function updateStatus(s) { currentStatus.value = s }

function toggleMaximize(target) {
  viewMode.value = viewMode.value === target ? 'split' : target
}

async function handleGoBack() {
  stopGraphRefresh()
  try {
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      try {
        await closeSimulationEnv({ simulation_id: currentSimulationId.value, timeout: 10 })
      } catch {
        await stopSimulation({ simulation_id: currentSimulationId.value }).catch(() => {})
      }
    } else if (isSimulating.value) {
      try {
        await stopSimulation({ simulation_id: currentSimulationId.value })
      } catch {
        // Best-effort cleanup before navigating back.
      }
    }
  } catch (err) {
    addLog(err.message)
  }
  router.push({ name: 'Simulation', params: { simulationId: currentSimulationId.value } })
}

function handleNextStep() { /* Step3Simulation navigates to Report itself */ }

async function loadSimulationData() {
  try {
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      try {
        const configRes = await getSimulationConfig(currentSimulationId.value)
        if (configRes.success && configRes.data?.time_config?.minutes_per_round) {
          minutesPerRound.value = configRes.data.time_config.minutes_per_round
        }
      } catch { /* non-fatal */ }
      if (simRes.data.project_id) {
        const projRes = await getProject(simRes.data.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          if (projRes.data.graph_id) await loadGraph(projRes.data.graph_id)
        }
      }
    }
  } catch (err) {
    addLog(err.message)
  }
}

async function loadGraph(graphId) {
  if (!isSimulating.value) graphLoading.value = true
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

let graphRefreshTimer = null
function startGraphRefresh() {
  if (graphRefreshTimer) return
  graphRefreshTimer = setInterval(refreshGraph, 30000)
}
function stopGraphRefresh() {
  if (graphRefreshTimer) { clearInterval(graphRefreshTimer); graphRefreshTimer = null }
}

watch(isSimulating, (val) => val ? startGraphRefresh() : stopGraphRefresh(), { immediate: true })

onMounted(() => {
  if (maxRounds.value) addLog(`max_rounds = ${maxRounds.value}`)
  loadSimulationData()
  pollGlobalStatus()
  statusTimer = setInterval(pollGlobalStatus, 3000)
})
onUnmounted(() => {
  stopGraphRefresh()
  if (statusTimer) clearInterval(statusTimer)
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
            step-counter="№ 03 / 05"
            :step-name="t('process.stepper.step3')"
            :status-kind="statusKind"
            :status-text="statusText"
          >
            <button
              v-if="statusKind === 'running' || statusKind === 'paused'"
              class="quick-pause"
              :class="{ paused: isPaused }"
              :disabled="isPauseToggling"
              :title="isPaused ? t('step3.controls.resume') : t('step3.controls.pause')"
              @click="togglePause"
            >
              <span v-if="isPaused">▶</span>
              <span v-else>❚❚</span>
              {{ isPaused ? t('step3.controls.resume') : t('step3.controls.pause') }}
            </button>
          </WorkspaceStepStatus>
        </template>
      </WorkspaceHeader>
    </template>

    <WorkspaceSplit :left-style="leftPanelStyle" :right-style="rightPanelStyle">
      <template #left>
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="3"
          :isSimulating="isSimulating"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </template>

      <template #right>
        <Step3Simulation
          :simulationId="currentSimulationId"
          :maxRounds="maxRounds"
          :minutesPerRound="minutesPerRound"
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
.quick-pause {
  background: transparent;
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-pill);
  padding: 4px 12px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  cursor: pointer;
  color: var(--ink-0);
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  transition: border-color 150ms ease, color 150ms ease;
}
.quick-pause:hover { color: var(--accent); border-color: var(--accent); }
.quick-pause.paused { color: var(--accent); border-color: var(--accent); }
.quick-pause:disabled { opacity: 0.5; cursor: wait; }
</style>
