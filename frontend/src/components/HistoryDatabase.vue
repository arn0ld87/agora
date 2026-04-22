<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { listRuns, getRunEvents, resumeRun, stopRun } from '../api/runs.js'
import { createSimulationBranch } from '../api/simulation.js'

const { locale } = useI18n()
const router = useRouter()

const runs = ref([])
const loading = ref(true)
const selectedRun = ref(null)
const runEvents = ref([])
const filters = ref({
  search: '',
  project: '',
  runType: '',
  status: '',
  branch: ''
})
const branchForm = ref({
  branch_name: '',
  llm_model: '',
  language: '',
  max_agents: '',
  enable_twitter: true,
  enable_reddit: true
})
const branchBusy = ref(false)
const actionBusy = ref(false)

async function loadRuns() {
  loading.value = true
  try {
    const res = await listRuns()
    runs.value = Array.isArray(res?.data) ? res.data : []
  } finally {
    loading.value = false
  }
}

async function selectRun(run) {
  selectedRun.value = run
  runEvents.value = []
  try {
    const [detail, events] = await Promise.all([
      listRuns({ limit: 1, entity_id: run.entity_id }).catch(() => null),
      getRunEvents(run.run_id).catch(() => null)
    ])
    if (events?.data) runEvents.value = events.data
    if (detail?.data?.[0]?.run_id === run.run_id) selectedRun.value = detail.data[0]
  } catch (_) {}
}

const projects = computed(() => {
  const ids = [...new Set(runs.value.map((run) => run.linked_ids?.project_id).filter(Boolean))]
  return ids.sort()
})

const branches = computed(() => {
  const ids = [...new Set(runs.value.map((run) => run.branch_label || run.metadata?.branch_name).filter(Boolean))]
  return ids.sort()
})

const filteredRuns = computed(() => {
  const q = filters.value.search.trim().toLowerCase()
  return runs.value.filter((run) => {
    const projectId = run.linked_ids?.project_id || ''
    const branch = run.branch_label || run.metadata?.branch_name || ''
    const matchSearch = !q || [run.run_id, run.entity_id, projectId, branch, run.message]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(q))
    const matchProject = !filters.value.project || projectId === filters.value.project
    const matchType = !filters.value.runType || run.run_type === filters.value.runType
    const matchStatus = !filters.value.status || run.status === filters.value.status
    const matchBranch = !filters.value.branch || branch === filters.value.branch
    return matchSearch && matchProject && matchType && matchStatus && matchBranch
  })
})

const groupedRuns = computed(() => {
  const groups = new Map()
  for (const run of filteredRuns.value) {
    const projectId = run.linked_ids?.project_id || 'unlinked'
    if (!groups.has(projectId)) groups.set(projectId, [])
    groups.get(projectId).push(run)
  }
  return [...groups.entries()].map(([projectId, items]) => ({
    projectId,
    items: items.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0))
  }))
})

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(locale.value === 'de' ? 'de-DE' : 'en-GB')
}

function routeForRun(run) {
  const linked = run.linked_ids || {}
  if (run.run_type === 'report_generate' && linked.report_id) {
    return { name: 'Report', params: { reportId: linked.report_id } }
  }
  if (run.run_type === 'simulation_run' && linked.simulation_id) {
    return { name: 'SimulationRun', params: { simulationId: linked.simulation_id } }
  }
  if ((run.run_type === 'simulation_prepare' || run.run_type === 'simulation_run') && linked.simulation_id) {
    return { name: 'Simulation', params: { simulationId: linked.simulation_id } }
  }
  if (linked.project_id) {
    return { name: 'Process', params: { projectId: linked.project_id } }
  }
  return null
}

function openRun(run) {
  selectRun(run)
  const target = routeForRun(run)
  if (target) router.push(target)
}

async function handleResume() {
  if (!selectedRun.value) return
  actionBusy.value = true
  try {
    const res = await resumeRun(selectedRun.value.run_id)
    await loadRuns()
    if (res?.data?.run_id) {
      const current = runs.value.find((item) => item.run_id === res.data.run_id) || selectedRun.value
      await selectRun(current)
    }
  } finally {
    actionBusy.value = false
  }
}

async function handleStop() {
  if (!selectedRun.value) return
  actionBusy.value = true
  try {
    await stopRun(selectedRun.value.run_id)
    await loadRuns()
    const current = runs.value.find((item) => item.run_id === selectedRun.value.run_id)
    if (current) await selectRun(current)
  } finally {
    actionBusy.value = false
  }
}

async function handleBranch() {
  const simulationId = selectedRun.value?.linked_ids?.simulation_id
  if (!simulationId || !branchForm.value.branch_name.trim()) return
  branchBusy.value = true
  try {
    const overrides = {
      enable_twitter: branchForm.value.enable_twitter,
      enable_reddit: branchForm.value.enable_reddit
    }
    if (branchForm.value.llm_model.trim()) overrides.llm_model = branchForm.value.llm_model.trim()
    if (branchForm.value.language.trim()) overrides.language = branchForm.value.language.trim()
    if (branchForm.value.max_agents !== '') overrides.max_agents = Number(branchForm.value.max_agents)
    const res = await createSimulationBranch(simulationId, {
      branch_name: branchForm.value.branch_name.trim(),
      copy_profiles: true,
      copy_report_artifacts: false,
      overrides
    })
    if (res?.data?.simulation_id) {
      router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id } })
    }
  } finally {
    branchBusy.value = false
  }
}

onMounted(loadRuns)
</script>

<template>
  <div class="run-center">
    <div class="section-head">
      <div class="left">
        <div class="num">06</div>
        <div class="k">Run Center</div>
      </div>
      <div class="copy">
        <h2>History, resume, branching</h2>
        <p class="sub">All graph builds, simulation prep/runs, and report generation in one persisted registry.</p>
      </div>
    </div>

    <div class="filters">
      <input v-model="filters.search" class="search" type="search" placeholder="Search run, project, branch" />
      <select v-model="filters.project">
        <option value="">All projects</option>
        <option v-for="projectId in projects" :key="projectId" :value="projectId">{{ projectId }}</option>
      </select>
      <select v-model="filters.runType">
        <option value="">All types</option>
        <option value="graph_build">graph_build</option>
        <option value="simulation_prepare">simulation_prepare</option>
        <option value="simulation_run">simulation_run</option>
        <option value="report_generate">report_generate</option>
      </select>
      <select v-model="filters.status">
        <option value="">All status</option>
        <option value="pending">pending</option>
        <option value="processing">processing</option>
        <option value="paused">paused</option>
        <option value="completed">completed</option>
        <option value="failed">failed</option>
        <option value="stopped">stopped</option>
      </select>
      <select v-model="filters.branch">
        <option value="">All branches</option>
        <option v-for="branch in branches" :key="branch" :value="branch">{{ branch }}</option>
      </select>
    </div>

    <div class="layout">
      <div class="table">
        <div v-if="loading" class="empty">Loading runs…</div>
        <div v-else-if="!groupedRuns.length" class="empty">No runs match the current filters.</div>

        <template v-else>
          <section v-for="group in groupedRuns" :key="group.projectId" class="group">
            <header class="group-head">
              <span>{{ group.projectId }}</span>
              <span>{{ group.items.length }} runs</span>
            </header>
            <button
              v-for="run in group.items"
              :key="run.run_id"
              class="row"
              :class="{ active: selectedRun?.run_id === run.run_id }"
              @click="selectRun(run)"
              @dblclick="openRun(run)"
            >
              <span class="type">{{ run.run_type }}</span>
              <span class="message">
                {{ run.message || run.entity_id }}
                <small>{{ run.run_id }} · {{ run.branch_label || 'main' }}</small>
              </span>
              <span class="status" :data-status="run.status">{{ run.status }}</span>
              <span class="progress">{{ run.progress ?? 0 }}%</span>
              <span class="updated">{{ formatDate(run.updated_at) }}</span>
            </button>
          </section>
        </template>
      </div>

      <aside class="drawer" v-if="selectedRun">
        <div class="drawer-head">
          <div>
            <div class="eyebrow">{{ selectedRun.run_type }}</div>
            <h3>{{ selectedRun.run_id }}</h3>
          </div>
          <button class="linkish" @click="openRun(selectedRun)">Open</button>
        </div>

        <div class="meta-grid">
          <div><span>Status</span><strong>{{ selectedRun.status }}</strong></div>
          <div><span>Progress</span><strong>{{ selectedRun.progress ?? 0 }}%</strong></div>
          <div><span>Entity</span><strong>{{ selectedRun.entity_id }}</strong></div>
          <div><span>Updated</span><strong>{{ formatDate(selectedRun.updated_at) }}</strong></div>
        </div>

        <p class="message-block">{{ selectedRun.message || 'No status message.' }}</p>
        <p v-if="selectedRun.error" class="error">{{ selectedRun.error }}</p>

        <div class="actions">
          <button
            v-if="selectedRun.resume_capability?.available"
            class="action"
            :disabled="actionBusy"
            @click="handleResume"
          >
            {{ selectedRun.resume_capability.label || 'Resume' }}
          </button>
          <button
            v-if="selectedRun.run_type === 'simulation_run' && ['processing', 'paused'].includes(selectedRun.status)"
            class="action alt"
            :disabled="actionBusy"
            @click="handleStop"
          >
            Stop run
          </button>
        </div>

        <div v-if="selectedRun.linked_ids?.simulation_id" class="branch-box">
          <h4>Create Branch</h4>
          <input v-model="branchForm.branch_name" type="text" placeholder="Branch name" />
          <input v-model="branchForm.llm_model" type="text" placeholder="LLM model override" />
          <div class="branch-row">
            <input v-model="branchForm.language" type="text" placeholder="language" />
            <input v-model="branchForm.max_agents" type="number" min="1" placeholder="max agents" />
          </div>
          <label><input v-model="branchForm.enable_twitter" type="checkbox" /> Twitter</label>
          <label><input v-model="branchForm.enable_reddit" type="checkbox" /> Reddit</label>
          <button class="action" :disabled="branchBusy" @click="handleBranch">Create branch</button>
        </div>

        <div class="artifacts" v-if="selectedRun.artifacts">
          <h4>Artifacts</h4>
          <pre>{{ JSON.stringify(selectedRun.artifacts, null, 2) }}</pre>
        </div>

        <div class="events" v-if="runEvents.length">
          <h4>Events</h4>
          <div v-for="event in runEvents.slice().reverse().slice(0, 8)" :key="`${event.timestamp}-${event.type}`" class="event">
            <strong>{{ event.type }}</strong>
            <span>{{ event.status }} · {{ event.progress ?? 0 }}%</span>
            <small>{{ formatDate(event.timestamp) }}</small>
            <p>{{ event.message }}</p>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.run-center { padding-top: var(--s-7); }
.copy .sub { color: var(--fg-muted); margin-top: var(--s-2); }
.filters {
  display: grid;
  grid-template-columns: 1.6fr repeat(4, minmax(0, 1fr));
  gap: var(--s-3);
  margin-top: var(--s-6);
}
.filters input, .filters select, .branch-box input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--rule);
  background: var(--paper-0);
  color: var(--ink-0);
  font-family: var(--ff-sans);
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(320px, 0.9fr);
  gap: var(--s-6);
  margin-top: var(--s-6);
}
.table, .drawer {
  border: 1px solid var(--rule);
  background: var(--paper-0);
}
.group-head, .row, .drawer-head {
  display: grid;
  align-items: center;
}
.group-head {
  grid-template-columns: 1fr auto;
  padding: 14px 18px;
  border-bottom: 1px solid var(--rule);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.row {
  width: 100%;
  grid-template-columns: 140px minmax(0, 1fr) 110px 70px 170px;
  gap: var(--s-4);
  padding: 16px 18px;
  border: 0;
  border-bottom: 1px solid var(--rule);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.row.active, .row:hover { background: var(--paper-1); }
.row .type, .row .progress, .row .updated, .status {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.row .message { min-width: 0; }
.row .message small {
  display: block;
  margin-top: 4px;
  color: var(--fg-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.status[data-status="failed"] { color: #b00020; }
.status[data-status="processing"] { color: var(--accent); }
.status[data-status="completed"] { color: #1e6a3b; }
.drawer { padding: 20px; }
.drawer-head {
  grid-template-columns: 1fr auto;
  gap: var(--s-3);
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-4);
}
.drawer-head h3 { margin: 4px 0 0; font-family: var(--ff-serif); }
.eyebrow { font-family: var(--ff-mono); font-size: 11px; letter-spacing: var(--ls-mono); text-transform: uppercase; color: var(--fg-muted); }
.linkish, .action {
  border: 1px solid var(--rule-strong);
  background: var(--paper-0);
  color: var(--ink-0);
  padding: 10px 14px;
  cursor: pointer;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.action.alt { background: var(--paper-1); }
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-4);
  margin-top: var(--s-4);
}
.meta-grid span { display: block; color: var(--fg-muted); font-size: 12px; }
.meta-grid strong { display: block; margin-top: 4px; }
.message-block, .error { margin-top: var(--s-4); }
.error { color: #b00020; }
.actions, .branch-row { display: flex; gap: var(--s-3); margin-top: var(--s-4); }
.branch-box, .artifacts, .events { margin-top: var(--s-6); }
.branch-box h4, .artifacts h4, .events h4 { margin-bottom: var(--s-3); font-family: var(--ff-serif); }
.branch-box label { display: block; margin-top: var(--s-2); color: var(--fg-muted); }
pre {
  max-height: 200px;
  overflow: auto;
  padding: 14px;
  background: var(--paper-1);
  border: 1px solid var(--rule);
  white-space: pre-wrap;
  word-break: break-word;
}
.event {
  padding: 12px 0;
  border-top: 1px solid var(--rule);
}
.event span, .event small {
  display: block;
  color: var(--fg-muted);
  margin-top: 4px;
}
.empty { padding: var(--s-7); color: var(--fg-muted); }
@media (max-width: 980px) {
  .filters, .layout { grid-template-columns: 1fr; }
  .row { grid-template-columns: 1fr; }
}
</style>
