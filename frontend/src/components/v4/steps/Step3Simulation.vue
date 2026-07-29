<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useEventStream } from '../../../composables/useEventStream'
import { traceIdToSigNozUrl } from '../../../observability/tracing'
import { useIncrementalLogPolling } from '../../../composables/useIncrementalLogPolling'
import { usePolling } from '../../../composables/usePolling'
import { useStickyScroll } from '../../../composables/useStickyScroll'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  startSimulation,
  stopSimulation,
  pauseSimulation,
  resumeSimulation,
  getRunStatus,
  getRunStatusDetail,
  getSimulationConsoleLog
} from '../../../api/simulation'
import { cancelRun } from '../../../api/runs'
import { generateReport } from '../../../api/report'
import { useRunModelResolver } from '@/composables/useRunModelResolver'
import { clearRunModelOverride } from '@/store/runModelOverride'
import Button from '@/components/v4/forms/Button.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import { tokenizeFeedText } from '../../../utils/feedHighlight'
import { isErrorLine } from '@/utils/errorLinePattern'
import { useSimFeed, clearSimFeed } from '../../../composables/useSimFeed'
import { useSimClock, clearSimClock } from '../../../composables/useSimClock'
import { getPendingUpload } from '../../../store/pendingUpload'
import SimulationProgressPanel from '../../step3/SimulationProgressPanel.vue'
import PersonaActionFeed from '../../step3/PersonaActionFeed.vue'
import SimulationToolPanel from '../../step3/SimulationToolPanel.vue'
import RunResourceMonitor from '../run-budget/RunResourceMonitor.vue'

const { t } = useI18n()
const router = useRouter()

const props = defineProps({
  simulationId: String,
  maxRounds: Number,
  simulationDays: Number,
  minutesPerRound: { type: Number, default: 30 },
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status', 'update-progress'])

let _lastProgressSnapshot = { paused: false, current_round: -1, total_rounds: -1 }

function maybeEmitProgress() {
  const paused = !!runStatus.value?.paused
  const current_round = runStatus.value?.current_round || 0
  const total_rounds = runStatus.value?.total_rounds || 0
  if (
    paused === _lastProgressSnapshot.paused &&
    current_round === _lastProgressSnapshot.current_round &&
    total_rounds === _lastProgressSnapshot.total_rounds
  ) return
  _lastProgressSnapshot = { paused, current_round, total_rounds }
  emit('update-progress', { paused, current_round, total_rounds })
}

const phase = ref(0) // 0 idle, 1 running, 2 done
const isStarting = ref(false)
const isStopping = ref(false)
const isPausing = ref(false)
const isCancelling = ref(false)
const isGeneratingReport = ref(false)
const runStatus = ref({})
const allActions = ref([])
const actionIds = ref(new Set())
// Server-Total-Count aus `actions_total`. Unabhängig von der Polling-Rate
// und springt nicht, wenn das (begrenzte) Sichtfenster gefüllt wird.
const totalActions = ref(0)
const scrollEl = ref(null)
const startError = ref(null)

// Issue #764 (Codex P1): echte RunRegistry-run_id aus /api/simulation/start
// Response. Backend liefert ``run_id`` separat von ``simulation_id``
// (simulation_run.py:468ff.); der Frontend-Type ``RunStatusResponse`` hat
// ``run_id`` als optionales Index-Signature-Feld. Ohne diesen Wert
// stammen Budget-Polls aus ``simulationId`` und schlagen mit 404 fehl,
// weil ``/api/runs/<run_id>`` die Registry-ID erwartet.
// Hinweis: <script setup> ist hier absichtlich ohne ``lang="ts"`` deklariert
// (siehe doStart-Kommentar) — daher keine TS-Generics an ref/computed, sonst
// parst JS ``ref < string | null > (null)`` als Vergleich und wirft zur
// Mount-Zeit ``ReferenceError: string is not defined``.
const runId = ref(null)
const effectiveRunId = computed(() => runId.value || props.simulationId || null)

const feedSticky = useStickyScroll(scrollEl)

// Feed density — persisted per browser
const FEED_DENSITY_KEY = 'agora.ui.feedDensity'
const feedDensity = ref(loadFeedDensity())

function loadFeedDensity() {
  try {
    const stored = localStorage.getItem(FEED_DENSITY_KEY)
    if (stored === 'comfort' || stored === 'compact') return stored
  } catch { /* localStorage unavailable */ }
  return 'comfort'
}

function setFeedDensity(value) {
  if (value !== 'comfort' && value !== 'compact') return
  feedDensity.value = value
  try { localStorage.setItem(FEED_DENSITY_KEY, value) } catch { /* ignore */ }
}

// Tool panel state
const TOOL_PANEL_KEY = 'agora.ui.toolPanel.open'

function loadToolPanelOpen() {
  try { return localStorage.getItem(TOOL_PANEL_KEY) === 'true' } catch { /* ignore */ }
  return false
}

const toolPanelOpen = ref(loadToolPanelOpen())
const toolPanelUnreadErrors = ref(0)
const toolPanelFilter = ref('all')
let _lastSeenConsoleLength = 0

function setToolPanelOpen(value) {
  toolPanelOpen.value = !!value
  try { localStorage.setItem(TOOL_PANEL_KEY, String(toolPanelOpen.value)) } catch { /* ignore */ }
  if (toolPanelOpen.value) {
    toolPanelUnreadErrors.value = 0
    _lastSeenConsoleLength = consoleLogs.value.length
  }
}

function toggleToolPanel() { setToolPanelOpen(!toolPanelOpen.value) }

const filteredConsoleLogs = computed(() => {
  if (toolPanelFilter.value !== 'errors') return consoleLogs.value
  return consoleLogs.value.filter(isErrorLine)
})

async function copyConsoleLineAsJson(line) {
  const payload = JSON.stringify({ line, ts: Date.now() })
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(payload)
    } else {
      const ta = document.createElement('textarea')
      ta.value = payload
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
  } catch { /* ignore */ }
}

function handleToolPanelHotkey(e) {
  if ((e.ctrlKey || e.metaKey) && (e.key === 'l' || e.key === 'L')) {
    e.preventDefault()
    toggleToolPanel()
  }
}

const consoleScrollEl = ref(null)
const consoleSticky = useStickyScroll(consoleScrollEl)

function setConsoleScrollRef(el) { consoleScrollEl.value = el instanceof Element ? el : null }
const {
  lines: consoleLogs,
  polling: consolePolling,
  reset: resetConsoleLogs,
} = useIncrementalLogPolling({
  fetcher: (sinceLine) => props.simulationId
    ? getSimulationConsoleLog(props.simulationId, sinceLine)
    : Promise.resolve(null),
  intervalMs: 2000,
  stickyScroll: consoleSticky,
})

watch(() => consoleLogs.value.length, (newLen) => {
  if (toolPanelOpen.value) {
    _lastSeenConsoleLength = newLen
    return
  }
  for (let i = _lastSeenConsoleLength; i < newLen; i += 1) {
    if (isErrorLine(consoleLogs.value[i])) toolPanelUnreadErrors.value += 1
  }
  _lastSeenConsoleLength = newLen
})

function addLog(msg) { emit('add-log', msg) }

const _feedStore = computed(() => useSimFeed(props.simulationId || '__unset__'))
const twitterPosts = computed(() => _feedStore.value.twitterPosts.value)
const redditPosts = computed(() => _feedStore.value.redditPosts.value)
const redditTree = computed(() => _feedStore.value.redditTree.value)

const _simClock = computed(() => useSimClock(props.simulationId || '__unset__'))
const currentSimTime = computed(() => _simClock.value.currentSimTime.value)
const simElapsedSec = computed(() => _simClock.value.elapsed.value)

// Autoritative (Connection, Modell)-Auswahl: tab-skopierter Run-Override vor
// routing/defaults.global_default. Wird beim Sim-Start als ``ai_model_ref``
// gesendet und bindet
// Base-URL + Secret derselben ProviderConnection an die OASIS-Route — kein
// .env-Fallback (Root Cause ``404 model MiniMax-M3 not found``).
const { resolveRunModel } = useRunModelResolver()

const statusStream = useEventStream(() => props.simulationId, {
  state: (msg) => applyRunStateEvent(msg?.payload),
  control: (msg) => applyControlEvent(msg?.payload),
  post_created: (data) => {
    if (!data) return
    _feedStore.value.ingest(data)
    _simClock.value.ingest(data)
  },
})
const { lastTraceId } = statusStream
const detailPolling = usePolling(pollDetail, 2500)

function resetState() {
  phase.value = 0
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  totalActions.value = 0
  resetConsoleLogs()
  toolPanelUnreadErrors.value = 0
  _lastSeenConsoleLength = 0
  startError.value = null
  // Issue #764 (Codex P1): RunRegistry-ID frisch aufnehmen — ein
  // re-run derselben simulation_id kann eine neue run_id liefern.
  runId.value = null
  isStarting.value = false
  isStopping.value = false
  isPausing.value = false
  _lastProgressSnapshot = { paused: false, current_round: -1, total_rounds: -1 }
  stopPolling()
}

async function doStart() {
  if (!props.simulationId) return
  resetState()
  isStarting.value = true
  emit('update-status', 'processing')
  try {
    const params = {
      simulation_id: props.simulationId,
      platform: 'parallel',
      enable_graph_memory_update: false
    }
    // Der Dashboard-Start (HeroNewRun) hat keinen Step2-Durchlauf — dessen
    // Slider-Wert liegt im pendingUpload-Store. Der Stepped-Flow übergibt
    // maxRounds als Prop und gewinnt. Vorher wurde der Slider-Wert nur beim
    // Ontologie-Upload gesendet, wo das Backend ihn still verwirft — die
    // eingestellte Rundenzahl hatte keinerlei Effekt (Bug: Slider ohne
    // Wirkung, Simulation lief immer auf total_simulation_hours).
    const effectiveMaxRounds = props.maxRounds ?? (getPendingUpload().numRounds || null)
    if (effectiveMaxRounds) params.max_rounds = effectiveMaxRounds
    // Issue #764: Optionale Run-Budgets aus dem Dashboard-Start (HeroNewRun)
    // werden unverändert an /api/simulation/start durchgereicht. Ohne Budget
    // bleibt das Feld weg — das Backend läuft dann ohne Limit.
    const pendingBudget = getPendingUpload().budget
    if (pendingBudget) params.budget = pendingBudget
    if (props.simulationDays) params.simulation_days = props.simulationDays
    // Autoritative (Connection, Modell)-Auswahl: Der transiente Dashboard-
    // Run-Override (HeroNewRun-Pick, store/runModelOverride) gewinnt vor dem
    // Kanon (routing/defaults.global_default). Die Auswahl wird als
    // ``ai_model_ref`` gesendet — das bindet Base-URL + Secret derselben
    // Connection an die OASIS-Route und schließt das .env-Fallback aus.
    // Ohne Override und ohne Kanon entscheidet das Backend-Routing; lokale
    // Legacy-Modellstrings sind keine Routingquelle mehr.
    const { ref: selection, usedRunOverride } = await resolveRunModel()
    if (selection && selection.provider_connection_id && selection.model_id) {
      params.ai_model_ref = {
        provider_connection_id: selection.provider_connection_id,
        model_id: selection.model_id,
        source: selection.source ?? 'explicit',
      }
    }
    addLog(t('step3.controls.starting'))
    const res = await startSimulation(params)
    if (res?.success) {
      // Issue #764 (Codex P1): Backend liefert die echte RunRegistry-ID
      // unter ``run_id``; Fallback auf simulationId lässt Legacy-Pfade
      // (z.B. Stub / Run-Bootstrap ohne echte Persist) weiterlaufen.
      // Cast vermieden, weil Step3Simulation <script setup> ohne
      // lang="ts" deklariert ist (vue-tsc behandelt den Block sonst
      // als JS und lehnt TS-Assertions ab).
      const data = res.data && typeof res.data === 'object' ? res.data : null
      const backendRunId = data && typeof (data).run_id === 'string' ? (data).run_id : null
      runId.value = backendRunId && backendRunId.length > 0 ? backendRunId : null
      // Consume-on-success: Der Dashboard-Override gilt genau für diesen
      // Start. Verhindert, dass ein späterer Start einer ANDEREN Simulation
      // im selben Tab den alten Override stillschweigend erbt.
      if (usedRunOverride) clearRunModelOverride()
      phase.value = 1
      addLog(t('step3.status.running', { current: 0, total: effectiveMaxRounds || '?' }))
      startPolling()
    } else {
      startError.value = res?.error || 'unknown'
      addLog(`${t('errors.simulationFailed')}: ${startError.value}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    startError.value = err.message
    addLog(err.message)
    emit('update-status', 'error')
  } finally {
    isStarting.value = false
  }
}

async function doStop() {
  if (!confirm(t('step3.controls.stopConfirm'))) return
  isStopping.value = true
  try {
    const res = await stopSimulation({ simulation_id: props.simulationId })
    if (res?.success) {
      addLog(t('step3.controls.stopped'))
      phase.value = 2
      emit('update-status', 'completed')
      stopPolling()
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isStopping.value = false
  }
}

async function doCancel() {
  if (!props.simulationId) return
  if (!confirm(t('step3.controls.cancelConfirm'))) return
  isCancelling.value = true
  try {
    const res = await cancelRun(props.simulationId)
    if (res?.success) addLog(t('step3.controls.cancelled'))
  } catch (err) {
    addLog(err.message)
  } finally {
    isCancelling.value = false
  }
}

async function doPauseResume() {
  if (!props.simulationId) return
  isPausing.value = true
  try {
    if (runStatus.value.paused) {
      const res = await resumeSimulation(props.simulationId)
      if (res?.success) {
        addLog(t('step3.controls.resume'))
        runStatus.value = { ...runStatus.value, paused: false }
        maybeEmitProgress()
      }
    } else {
      const res = await pauseSimulation(props.simulationId)
      if (res?.success) {
        addLog(t('step3.controls.pauseHint'))
        runStatus.value = { ...runStatus.value, paused: true }
        maybeEmitProgress()
      }
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isPausing.value = false
  }
}

function startPolling() {
  statusStream.start()
  void detailPolling.start({ immediate: true })
  void consolePolling.start({ immediate: true })
}
function stopPolling() {
  statusStream.stop()
  detailPolling.stop()
  consolePolling.stop()
}

function promoteToCompletedPhase(status, data) {
  if (phase.value === 2) return
  phase.value = 2
  if (status === 'completed' || status === 'stopped') {
    addLog(t('step3.status.completed', { total: data?.current_round }))
    emit('update-status', 'completed')
  } else {
    emit('update-status', 'error')
  }
  stopPolling()
}

function applyRunStateEvent(data) {
  if (!data || typeof data !== 'object') return
  runStatus.value = { ...runStatus.value, ...data }
  const status = data?.runner_status
  if (status === 'completed' || status === 'failed') {
    promoteToCompletedPhase(status, data)
  }
  maybeEmitProgress()
}

function applyControlEvent(data) {
  if (!data || typeof data !== 'object') return
  runStatus.value = { ...runStatus.value, paused: !!data.paused }
  maybeEmitProgress()
}

async function pollStatus() {
  try {
    const res = await getRunStatus(props.simulationId)
    if (res?.success) applyRunStateEvent(res.data)
  } catch { /* swallow */ }
}

async function pollDetail() {
  try {
    const res = await getRunStatusDetail(props.simulationId)
    if (!res?.success) return
    const detailStatus = res.data?.runner_status
    if (detailStatus) {
      runStatus.value = {
        ...runStatus.value,
        runner_status: detailStatus,
        current_round: res.data?.current_round ?? runStatus.value.current_round,
        total_rounds: res.data?.total_rounds ?? runStatus.value.total_rounds,
      }
      if (detailStatus === 'completed' || detailStatus === 'failed' || detailStatus === 'stopped') {
        promoteToCompletedPhase(detailStatus, res.data)
      }
      maybeEmitProgress()
    }
    // Der Endpoint liefert keine vollständige `all_actions`-Liste mehr (das
    // wurde mit dem Pagination-Fix entfernt) — nur die paginierten `actions`.
    // Wir deduplizieren deshalb clientseitig über Zeitstempel und Inhalt.
    // Ohne den Zeitstempel im Schlüssel würden zwei identische Aktionen
    // desselben Agenten in derselben Runde fälschlich als Duplikat
    // verworfen. Der Gesamtzähler kommt aus `actions_total`, nicht aus der
    // Länge des (begrenzten) Sichtfensters.
    if (Array.isArray(res.data?.actions)) {
      let appended = 0
      for (const a of res.data.actions) {
        const key = `${a.round_num}-${a.platform}-${a.agent_id}-${a.action_type}-${a.timestamp}-${(a.action_args?.content || '').length}`
        if (!actionIds.value.has(key)) {
          actionIds.value.add(key)
          if (a.action_args?.content) a._tokens = tokenizeFeedText(a.action_args.content)
          allActions.value.push(a)
          appended += 1
        }
      }
      if (appended > 0) nextTick(() => feedSticky.markAppended(appended))
    }
    if (typeof res.data?.actions_total === 'number') {
      totalActions.value = res.data.actions_total
    }
  } catch { /* swallow */ }
}

const statusLabel = computed(() => {
  if (phase.value === 0) return t('step3.status.ready')
  if (phase.value === 2) {
    return runStatus.value.runner_status === 'failed'
      ? t('step3.status.failed')
      : t('step3.status.completed', { total: runStatus.value.current_round || '?' })
  }
  if (runStatus.value.paused) {
    return t('step3.status.paused', { current: runStatus.value.current_round || 0, total: runStatus.value.total_rounds || props.maxRounds || getPendingUpload().numRounds || '?' })
  }
  return t('step3.status.running', { current: runStatus.value.current_round || 0, total: runStatus.value.total_rounds || props.maxRounds || getPendingUpload().numRounds || '?' })
})

const statusKind = computed(() => {
  if (phase.value === 0) return 'idle'
  if (phase.value === 2) return runStatus.value.runner_status === 'failed' ? 'error' : 'done'
  if (runStatus.value.paused) return 'paused'
  return 'running'
})

// Issue #764: Der RunResourceMonitor erwartet kanonische Run-Statuswerte
// (pending/processing/…). Step3 denkt in Phasen — Mapping: laufend →
// processing, abgeschlossen → completed, vor dem Start → pending.
const budgetMonitorStatus = computed(() => {
  if (phase.value === 1) return 'processing'
  if (phase.value === 2) return 'completed'
  return 'pending'
})

const twitterActions = computed(() => allActions.value.filter((a) => a.platform === 'twitter').length)
const redditActions = computed(() => allActions.value.filter((a) => a.platform === 'reddit').length)

async function goReport() {
  if (!props.simulationId) return
  isGeneratingReport.value = true
  try {
    const payload = { simulation_id: props.simulationId }
    const res = await generateReport(payload)
    if (res?.success && res.data?.report_id) {
      // Issue #764 (Codex P1): run_id als Query-Param an die Report-Route
      // durchreichen, damit Step4Report.loadRunUsage /api/runs/<run_id>
      // anstelle der simulation_id pollt. Die simulation_id aus
      // Route-Params bleibt dem Backend als identifier erhalten; der
      // run_id-Query ist nur die Registry-Anschrift für die Budget-
      // Verbrauchsdarstellung.
      const runIdForReport = effectiveRunId.value
      router.push({
        name: 'Report',
        params: { reportId: res.data.report_id },
        query: runIdForReport && runIdForReport !== props.simulationId ? { runId: runIdForReport } : undefined,
      })
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isGeneratingReport.value = false
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleToolPanelHotkey)
  await pollStatus()
  if (runStatus.value?.runner_status === 'running') {
    phase.value = 1
    startPolling()
  } else if (runStatus.value?.runner_status === 'completed') {
    phase.value = 2
    pollDetail()
  }
})
onUnmounted(() => {
  window.removeEventListener('keydown', handleToolPanelHotkey)
  stopPolling()
  if (props.simulationId) {
    clearSimFeed(props.simulationId)
    clearSimClock(props.simulationId)
  }
})

watch(() => props.simulationId, (newId, oldId) => {
  if (oldId && oldId !== newId) {
    clearSimFeed(oldId)
    clearSimClock(oldId)
  }
})
</script>

<template>
  <div class="step-panel">
    <div ref="scrollEl" class="scroll">

      <!-- Card 1: Controls -->
      <article class="card" :class="{ 'is-active': phase === 1 }">
        <header class="card-head">
          <Kicker num="01">{{ t('step3.title') }}</Kicker>
          <Badge :tone="statusKind === 'running' ? 'blue' : statusKind === 'paused' ? 'orange' : statusKind === 'done' ? 'green' : statusKind === 'error' ? 'red' : 'gray'" :dot="statusKind === 'running'">
            {{ statusLabel }}
          </Badge>
        </header>
        <p class="card-desc">{{ t('step3.sub') }}</p>

        <div class="actions">
          <Button variant="ghost" :disabled="phase === 1" @click="$emit('go-back')">← {{ t('common.back') }}</Button>
          <Button
            v-if="phase === 0"
            variant="primary"
            arrow
            :loading="isStarting"
            @click="doStart"
          >{{ t('step3.controls.start') }}</Button>
          <template v-else-if="phase === 1">
            <Button variant="ghost" :loading="isPausing" @click="doPauseResume">
              {{ runStatus.paused ? t('step3.controls.resume') : t('step3.controls.pause') }}
            </Button>
            <Button variant="danger" :loading="isStopping" @click="doStop">{{ t('step3.controls.stop') }}</Button>
            <Button variant="ghost" :loading="isCancelling" :title="t('step3.controls.cancelConfirm')" @click="doCancel">{{ t('step3.controls.cancel') }}</Button>
          </template>
          <Button v-else variant="primary" arrow :loading="isGeneratingReport" @click="goReport">{{ t('step3.next') }}</Button>
        </div>
        <a
          v-if="lastTraceId"
          :href="traceIdToSigNozUrl(lastTraceId)"
          target="_blank"
          rel="noopener noreferrer"
          class="trace-link"
        >
          {{ t('observability.viewTrace', { id: lastTraceId.slice(0, 8) }) }}
        </a>
      </article>

      <!-- Card 2: Stats (extracted to SimulationProgressPanel) -->
      <SimulationProgressPanel
        v-if="phase >= 1"
        :total-actions="totalActions"
        :twitter-actions="twitterActions"
        :reddit-actions="redditActions"
        :current-sim-time="currentSimTime"
        :sim-elapsed-sec="simElapsedSec"
      />

      <!-- Issue #764: Live-Verbrauch vs. Budget (pollt /api/runs/<id>) -->
      <RunResourceMonitor
        v-if="phase >= 1 && effectiveRunId"
        :run-id="effectiveRunId"
        :status="budgetMonitorStatus"
      />

      <!-- Card 3: Live feed (extracted to PersonaActionFeed) -->
      <PersonaActionFeed
        v-if="phase >= 1"
        :all-actions-count="allActions.length"
        :twitter-posts="twitterPosts"
        :reddit-posts="redditPosts"
        :reddit-tree="redditTree"
        :feed-density="feedDensity"
        :tool-panel-open="toolPanelOpen"
        :tool-panel-unread-errors="toolPanelUnreadErrors"
        @set-density="setFeedDensity"
        @toggle-tool-panel="toggleToolPanel"
      />

      <!-- Card 4: Tool-Calls + Errors-Panel (extracted to SimulationToolPanel) -->
      <SimulationToolPanel
        v-if="phase >= 1 && toolPanelOpen"
        :console-logs="consoleLogs"
        :tool-panel-filter="toolPanelFilter"
        :filtered-console-logs="filteredConsoleLogs"
        :console-unread-count="consoleSticky.unreadCount.value"
        :console-scroll-ref="setConsoleScrollRef"
        @update:tool-panel-filter="toolPanelFilter = $event"
        @copy-line="copyConsoleLineAsJson"
        @scroll-to-bottom="consoleSticky.scrollToBottom"
      />

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
.actions { display: flex; gap: var(--s-3); justify-content: flex-end; border-top: 1px solid var(--rule); padding-top: var(--s-4); }
.trace-link { display: inline-block; font-family: var(--ff-mono); font-size: 11px; color: var(--accent); text-decoration: underline; text-underline-offset: 2px; opacity: 0.75; transition: opacity 120ms ease; }
.trace-link:hover { opacity: 1; }
</style>