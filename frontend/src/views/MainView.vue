<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphPanel from '../components/GraphPanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import WorkspaceBrandLink from '../layouts/WorkspaceBrandLink.vue'
import WorkspaceHeader from '../layouts/WorkspaceHeader.vue'
import WorkspaceLayout from '../layouts/WorkspaceLayout.vue'
import WorkspaceModeSwitch from '../layouts/WorkspaceModeSwitch.vue'
import WorkspaceSplit from '../layouts/WorkspaceSplit.vue'
import WorkspaceStepStatus from '../layouts/WorkspaceStepStatus.vue'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// Layout: graph | split | workbench
const viewMode = ref('split')

// Wizard state — Steps 1+2 live in MainView; 3-5 jump to dedicated views.
const currentStep = ref(1)
const workspaceModes = [
  { value: 'graph', label: 'Graph' },
  { value: 'split', label: 'Split' },
  { value: 'workbench', label: 'Workbench' },
]
const stepLabels = computed(() => [
  t('process.stepper.step1'),
  t('process.stepper.step2'),
  t('process.stepper.step3'),
  t('process.stepper.step4'),
  t('process.stepper.step5'),
])

// Project + graph state (unchanged from prior version)
const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const currentPhase = ref(-1) // -1 upload, 0 ontology, 1 build, 2 done
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])

let pollTimer = null
let graphPollTimer = null

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

const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'done'
  if (currentPhase.value >= 0) return 'running'
  return 'idle'
})
const statusText = computed(() => {
  if (error.value) return t('common.error')
  if (currentPhase.value >= 2) return t('common.ready')
  if (currentPhase.value === 1) return t('step1.build.running')
  if (currentPhase.value === 0) return t('step1.ontology.generate')
  return t('common.starting')
})

function addLog(msg) {
  const now = new Date()
  const time = now.toTimeString().slice(0, 8) + '.' + String(now.getMilliseconds()).padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 100) systemLogs.value.shift()
}

function toggleMaximize(target) {
  viewMode.value = viewMode.value === target ? 'split' : target
}

function handleNextStep(params = {}) {
  if (currentStep.value === 2) {
    // Step 2 → 3 is a separate route (SimulationView).
    if (route.params.projectId && projectData.value) {
      // simulation_id should be in params; otherwise fall back to listing.
      const simId = params.simulationId
      if (simId) {
        router.push({ name: 'Simulation', params: { simulationId: simId } })
        return
      }
    }
  }
  if (currentStep.value < 5) {
    currentStep.value++
    addLog(`${t('common.next')}: ${stepLabels.value[currentStep.value - 1]}`)
  }
}

function handleGoBack() {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(`${t('common.back')}: ${stepLabels.value[currentStep.value - 1]}`)
  }
}

async function initProject() {
  addLog('Pipeline init.')
  if (currentProjectId.value === 'new') {
    await handleNewProject()
  } else {
    await loadProject()
  }
}

async function handleNewProject() {
  const pending = getPendingUpload()
  if (!pending.isPending || pending.files.length === 0) {
    error.value = 'No pending files found.'
    addLog('Error: no pending files for new project.')
    return
  }
  try {
    loading.value = true
    currentPhase.value = 0
    ontologyProgress.value = { message: t('common.processing') }
    addLog(t('common.processing'))
    const formData = new FormData()
    pending.files.forEach((f) => formData.append('files', f))
    formData.append('simulation_requirement', pending.simulationRequirement)
    const res = await generateOntology(formData)
    if (res.success) {
      clearPendingUpload()
      currentProjectId.value = res.data.project_id
      projectData.value = res.data
      router.replace({ name: 'Process', params: { projectId: res.data.project_id } })
      ontologyProgress.value = null
      addLog(`Ontology ready (project ${res.data.project_id}).`)
      await startBuildGraph()
    } else {
      error.value = res.error || t('errors.unknown')
      addLog(`Error: ${error.value}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception: ${err.message}`)
  } finally {
    loading.value = false
  }
}

async function loadProject() {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}…`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status)
      addLog(`Project status: ${res.data.status}`)
      if (res.data.status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (res.data.status === 'graph_building' && res.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (res.data.status === 'graph_completed' && res.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(res.data.graph_id)
      }
    } else {
      error.value = res.error
      addLog(`Error loading project: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception: ${err.message}`)
  } finally {
    loading.value = false
  }
}

function updatePhaseByStatus(status) {
  switch (status) {
    case 'created':
    case 'ontology_generated': currentPhase.value = 0; break
    case 'graph_building': currentPhase.value = 1; break
    case 'graph_completed': currentPhase.value = 2; break
    case 'failed': error.value = 'Project failed'; break
  }
}

async function startBuildGraph() {
  try {
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: t('step1.build.running') }
    addLog(t('step1.build.running'))
    const res = await buildGraph({ project_id: currentProjectId.value })
    if (res.success) {
      addLog(`Build task: ${res.data.task_id}`)
      startGraphPolling()
      startPollingTask(res.data.task_id)
    } else {
      error.value = res.error
      addLog(`Error: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception: ${err.message}`)
  }
}

function startGraphPolling() {
  fetchGraphData()
  graphPollTimer = setInterval(fetchGraphData, 10000)
}

async function fetchGraphData() {
  try {
    const projRes = await getProject(currentProjectId.value)
    if (projRes.success && projRes.data.graph_id) {
      const gRes = await getGraphData(projRes.data.graph_id)
      if (gRes.success) {
        graphData.value = gRes.data
      }
    }
  } catch (err) {
    console.warn('Graph fetch error:', err)
  }
}

function startPollingTask(taskId) {
  pollTaskStatus(taskId)
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
}

async function pollTaskStatus(taskId) {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data
      if (task.message && task.message !== buildProgress.value?.message) {
        addLog(task.message)
      }
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      if (task.status === 'completed') {
        addLog(t('step1.build.completed'))
        stopPolling()
        stopGraphPolling()
        currentPhase.value = 2
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
          projectData.value = projRes.data
          await loadGraph(projRes.data.graph_id)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        error.value = task.error
        addLog(`Build failed: ${task.error}`)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

async function loadGraph(graphId) {
  graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (res.success) graphData.value = res.data
  } catch (e) {
    addLog(`Exception loading graph: ${e.message}`)
  } finally {
    graphLoading.value = false
  }
}

function refreshGraph() {
  if (projectData.value?.graph_id) loadGraph(projectData.value.graph_id)
}

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }
function stopGraphPolling() { if (graphPollTimer) { clearInterval(graphPollTimer); graphPollTimer = null } }

onMounted(initProject)
onUnmounted(() => { stopPolling(); stopGraphPolling() })
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
            :step-counter="`№ 0${currentStep} / 05`"
            :step-name="stepLabels[currentStep - 1]"
            :status-kind="statusClass === 'done' ? 'done' : statusClass === 'error' ? 'error' : 'running'"
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
          :currentPhase="currentPhase"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </template>

      <template #right>
        <Step1GraphBuild
          v-if="currentStep === 1"
          :currentPhase="currentPhase"
          :projectData="projectData"
          :ontologyProgress="ontologyProgress"
          :buildProgress="buildProgress"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @next-step="handleNextStep"
        />
        <Step2EnvSetup
          v-else-if="currentStep === 2"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
        />
      </template>
    </WorkspaceSplit>
  </WorkspaceLayout>
</template>

<style scoped>
</style>
