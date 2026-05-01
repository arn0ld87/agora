<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useEventStream } from '../composables/useEventStream'
import { useIncrementalLogPolling } from '../composables/useIncrementalLogPolling'
import { usePolling } from '../composables/usePolling'
import { useStickyScroll } from '../composables/useStickyScroll'
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
} from '../api/simulation'
import { generateReport } from '../api/report'
import Btn from './ui/Btn.vue'
import Badge from './ui/Badge.vue'
import Kicker from './ui/Kicker.vue'
import StickyScrollBanner from './ui/StickyScrollBanner.vue'

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

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

const phase = ref(0) // 0 idle, 1 running, 2 done
const isStarting = ref(false)
const isStopping = ref(false)
const isPausing = ref(false)
const isGeneratingReport = ref(false)
const runStatus = ref({})
const allActions = ref([])
const actionIds = ref(new Set())
const scrollEl = ref(null)
const startError = ref(null)

// Issue #130: Sticky-Scroll im Live-Feed. Nutzer-Scrollback wird respektiert,
// neue Beiträge werden im Banner gezählt statt blind ans Ende zu springen.
const feedSticky = useStickyScroll(scrollEl)

// Issue #130 SUB2: Density-Toggle für den Live-Feed; Persistenz pro Browser.
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

// Issue #39 — Console-Logs werden über das useIncrementalLogPolling-Composable
// inkrementell gefetcht, an `consoleLogs` gehängt und automatisch zum Bottom
// gescrollt. Cursor und Append-/Scroll-Logik liegen im Composable.
const {
  lines: consoleLogs,
  containerRef: consoleScrollEl,
  polling: consolePolling,
  reset: resetConsoleLogs,
} = useIncrementalLogPolling({
  fetcher: (sinceLine) => props.simulationId
    ? getSimulationConsoleLog(props.simulationId, sinceLine)
    : Promise.resolve(null),
  intervalMs: 2000,
})

function addLog(msg) { emit('add-log', msg) }

// Issue #9 Phase C: run-state now arrives via SSE (backend subscribes to
// the event bus), so the 2.5 s status-polling loop is gone. Detail + console
// stay on HTTP polls — they read different artifacts.
const statusStream = useEventStream(() => props.simulationId, {
  state: (msg) => applyRunStateEvent(msg?.payload),
  control: (msg) => applyControlEvent(msg?.payload),
})
const detailPolling = usePolling(pollDetail, 2500)

function resetState() {
  phase.value = 0
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  resetConsoleLogs()
  startError.value = null
  isStarting.value = false
  isStopping.value = false
  isPausing.value = false
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
    if (props.maxRounds) params.max_rounds = props.maxRounds
    if (props.simulationDays) params.simulation_days = props.simulationDays
    addLog(t('step3.controls.starting'))
    const res = await startSimulation(params)
    if (res?.success) {
      phase.value = 1
      addLog(t('step3.status.running', { current: 0, total: props.maxRounds || '?' }))
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

async function doPauseResume() {
  if (!props.simulationId) return
  isPausing.value = true
  try {
    if (runStatus.value.paused) {
      const res = await resumeSimulation(props.simulationId)
      if (res?.success) {
        addLog(t('step3.controls.resume'))
        runStatus.value = { ...runStatus.value, paused: false }
      }
    } else {
      const res = await pauseSimulation(props.simulationId)
      if (res?.success) {
        addLog(t('step3.controls.pauseHint'))
        runStatus.value = { ...runStatus.value, paused: true }
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

function applyRunStateEvent(data) {
  if (!data || typeof data !== 'object') return
  runStatus.value = { ...runStatus.value, ...data }
  const status = data?.runner_status
  if (status === 'completed') {
    phase.value = 2
    addLog(t('step3.status.completed', { total: data.current_round }))
    emit('update-status', 'completed')
    stopPolling()
  } else if (status === 'failed') {
    phase.value = 2
    emit('update-status', 'error')
    stopPolling()
  }
}

function applyControlEvent(data) {
  if (!data || typeof data !== 'object') return
  // Merge pause flag into the visible status so the Pause/Resume button
  // flips on the same tick the backend saw the change.
  runStatus.value = { ...runStatus.value, paused: !!data.paused }
}

async function pollStatus() {
  // Hydration fallback: the SSE endpoint replays the retained snapshot
  // on connect, so this only runs once on mount before the stream opens
  // (or if the stream failed and we want a last-gasp state read).
  try {
    const res = await getRunStatus(props.simulationId)
    if (res?.success) applyRunStateEvent(res.data)
  } catch { /* swallow */ }
}

async function pollDetail() {
  try {
    const res = await getRunStatusDetail(props.simulationId)
    if (res?.success && Array.isArray(res.data?.all_actions)) {
      let appended = 0
      for (const a of res.data.all_actions) {
        const key = `${a.round_num}-${a.platform}-${a.agent_id}-${a.action_type}`
        if (!actionIds.value.has(key)) {
          actionIds.value.add(key)
          allActions.value.push(a)
          appended += 1
        }
      }
      if (appended > 0) {
        // Sticky-Scroll: nur ans Ende springen, wenn Nutzer dort klebt;
        // sonst Banner-Counter erhöhen.
        nextTick(() => feedSticky.markAppended(appended))
      }
    }
  } catch { /* swallow */ }
}

const statusLabel = computed(() => {
  if (phase.value === 0) return t('step3.status.ready')
  if (phase.value === 2) {
    return runStatus.value.runner_status === 'failed' ? t('step3.status.failed') : t('step3.status.completed', { total: runStatus.value.current_round || '?' })
  }
  if (runStatus.value.paused) {
    return t('step3.status.paused', { current: runStatus.value.current_round || 0, total: runStatus.value.total_rounds || props.maxRounds || '?' })
  }
  return t('step3.status.running', { current: runStatus.value.current_round || 0, total: runStatus.value.total_rounds || props.maxRounds || '?' })
})

const statusKind = computed(() => {
  if (phase.value === 0) return 'idle'
  if (phase.value === 2) return runStatus.value.runner_status === 'failed' ? 'error' : 'done'
  if (runStatus.value.paused) return 'paused'
  return 'running'
})

const totalActions = computed(() => allActions.value.length)
const twitterActions = computed(() => allActions.value.filter((a) => a.platform === 'twitter').length)
const redditActions = computed(() => allActions.value.filter((a) => a.platform === 'reddit').length)

async function goReport() {
  if (!props.simulationId) return
  isGeneratingReport.value = true
  try {
    // Reuse the model the user picked for Step 2 (Report-specific override
    // can be set in Step 4). 'default' or empty → server uses LLM_MODEL_NAME.
    const payload = { simulation_id: props.simulationId }
    const stored = localStorage.getItem('agora.reportModel') || localStorage.getItem('agora.lastModel')
    if (stored && stored !== 'default' && stored !== 'custom') {
      payload.llm_model = stored
    }
    const res = await generateReport(payload)
    if (res?.success && res.data?.report_id) {
      router.push({ name: 'Report', params: { reportId: res.data.report_id } })
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isGeneratingReport.value = false
  }
}

onMounted(async () => {
  // If simulation already running on mount, hydrate.
  await pollStatus()
  if (runStatus.value?.runner_status === 'running') {
    phase.value = 1
    startPolling()
  } else if (runStatus.value?.runner_status === 'completed') {
    phase.value = 2
    pollDetail()
  }
})
onUnmounted(stopPolling)
</script>

<template>
  <div class="step-panel">
    <div class="scroll">

      <!-- Card 1: Controls -->
      <article class="card" :class="{ 'is-active': phase === 1 }">
        <header class="card-head">
          <Kicker num="01">{{ t('step3.title') }}</Kicker>
          <Badge :variant="statusKind === 'running' ? 'accent' : statusKind === 'paused' ? 'outline' : statusKind === 'done' ? 'solid' : 'ghost'" :dot="statusKind === 'running'">
            {{ statusLabel }}
          </Badge>
        </header>
        <p class="card-desc">{{ t('step3.sub') }}</p>

        <div class="actions">
          <Btn variant="ghost" :disabled="phase === 1" @click="$emit('go-back')">← {{ t('common.back') }}</Btn>
          <Btn
            v-if="phase === 0"
            variant="primary"
            arrow
            :loading="isStarting"
            @click="doStart"
          >{{ t('step3.controls.start') }}</Btn>
          <template v-else-if="phase === 1">
            <Btn
              variant="ghost"
              :loading="isPausing"
              @click="doPauseResume"
            >
              {{ runStatus.paused ? t('step3.controls.resume') : t('step3.controls.pause') }}
            </Btn>
            <Btn
              variant="danger"
              :loading="isStopping"
              @click="doStop"
            >{{ t('step3.controls.stop') }}</Btn>
          </template>
          <Btn
            v-else
            variant="primary"
            arrow
            :loading="isGeneratingReport"
            @click="goReport"
          >{{ t('step3.next') }}</Btn>
        </div>
      </article>

      <!-- Card 2: Stats -->
      <article class="card" v-if="phase >= 1">
        <header class="card-head">
          <Kicker num="02">{{ t('step3.feed.title') }}</Kicker>
          <span class="meta">{{ t('step3.feed.actions', { count: totalActions }) }}</span>
        </header>
        <div class="stats-grid">
          <div class="stat">
            <span class="stat-value">{{ totalActions }}</span>
            <span class="stat-label">{{ t('step3.feed.actions', { count: '' }).replace(':', '').trim() }}</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ twitterActions }}</span>
            <span class="stat-label">Twitter</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ redditActions }}</span>
            <span class="stat-label">Reddit</span>
          </div>
        </div>
      </article>

      <!-- Card 3: Live feed + terminal (two-pane) -->
      <article class="card" v-if="phase >= 1">
        <header class="card-head">
          <Kicker num="03" accent>{{ t('step3.feed.title') }}</Kicker>
          <div class="log-meta">
            <Badge variant="ghost">{{ allActions.length }} actions</Badge>
            <Badge variant="ghost">{{ consoleLogs.length }} console</Badge>
          </div>
        </header>
        <div class="logs-grid">
          <div class="log-pane">
            <div class="log-pane-head">
              <span class="meta">Live-Feed</span>
              <div class="density-toggle" role="group" :aria-label="t('step3.feed.density.label')">
                <button
                  type="button"
                  class="density-btn"
                  :class="{ active: feedDensity === 'comfort' }"
                  :aria-pressed="feedDensity === 'comfort'"
                  @click="setFeedDensity('comfort')"
                >{{ t('step3.feed.density.comfort') }}</button>
                <button
                  type="button"
                  class="density-btn"
                  :class="{ active: feedDensity === 'compact' }"
                  :aria-pressed="feedDensity === 'compact'"
                  @click="setFeedDensity('compact')"
                >{{ t('step3.feed.density.compact') }}</button>
              </div>
              <span class="meta">{{ allActions.length }}</span>
            </div>
            <div class="log-pane-scroll-wrap">
              <div
                ref="scrollEl"
                class="feed log-block log-pane-body"
                :class="['density-' + feedDensity]"
              >
                <div v-if="!allActions.length" class="meta">{{ t('step3.feed.empty') }}</div>
                <div v-for="(a, i) in allActions" :key="i" class="feed-line">
                  <span class="ts">[R{{ a.round_num }} · {{ a.platform.toUpperCase() }}]</span>
                  <span class="who">{{ a.agent_name || ('agent_' + a.agent_id) }}</span>
                  <span class="act">{{ a.action_type }}</span>
                  <span class="content" v-if="a.action_args?.content">— {{ a.action_args.content }}</span>
                </div>
              </div>
              <StickyScrollBanner
                :count="feedSticky.unreadCount.value"
                @jump="feedSticky.scrollToBottom"
              />
            </div>
          </div>
          <div class="log-pane">
            <div class="log-pane-head">
              <span class="meta">Terminal (stdout/stderr)</span>
              <span class="meta">{{ consoleLogs.length }}</span>
            </div>
            <div ref="consoleScrollEl" class="log-block log-pane-body">
              <div v-if="!consoleLogs.length" class="meta">Warte auf Ausgabe…</div>
              <div v-for="(line, i) in consoleLogs" :key="'c' + i" class="console-line">
                {{ line }}
              </div>
            </div>
          </div>
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
.actions {
  display: flex; gap: var(--s-3); justify-content: flex-end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-4);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--rule);
}
.stat {
  padding: var(--s-3) var(--s-3) var(--s-3) 0;
  border-right: 1px solid var(--rule);
}
.stat:last-child { border-right: 0; }
.stat-value {
  display: block;
  font-family: var(--ff-serif);
  font-size: var(--fs-32);
  color: var(--fg);
  line-height: 1;
}
.stat-label {
  display: block;
  margin-top: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.feed {
  overflow-y: auto;
}
.feed-line {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  line-height: 1.5;
  color: var(--mono-50);
  margin-bottom: var(--s-2);
  word-wrap: break-word;
  max-width: 75ch;
}
.feed.density-compact .feed-line {
  font-size: 11px;
  line-height: 1.35;
  margin-bottom: 4px;
}
.feed.density-comfort .feed-line {
  font-size: var(--fs-13, 13px);
  line-height: 1.6;
  margin-bottom: var(--s-3);
}
.feed-line .ts { color: var(--accent); }
.feed-line .who { color: var(--status-warn); margin: 0 var(--s-2); }
.feed-line .act { color: var(--mono-300); }
.feed-line .content { color: var(--mono-100); }

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
  min-width: 0;
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
  /* Issue #130 SUB2: Feed-/Console-Panes deutlich größer; floor 480 px,
     wachsen bis 60 % Viewport, Cap bei 720 px für sehr große Monitore. */
  min-height: 480px;
  max-height: clamp(480px, 60vh, 720px);
  overflow-y: auto;
}

.density-toggle {
  display: inline-flex;
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  overflow: hidden;
}

.density-btn {
  background: transparent;
  border: 0;
  padding: 4px 10px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  cursor: pointer;
  transition: background 120ms ease, color 120ms ease;
}

.density-btn + .density-btn {
  border-left: 1px solid var(--rule);
}

.density-btn:hover {
  color: var(--fg);
}

.density-btn.active {
  background: var(--accent);
  color: var(--bg);
}
.console-line {
  font-family: var(--ff-mono);
  font-size: 11px;
  color: var(--mono-100);
  word-wrap: break-word;
  white-space: pre-wrap;
  margin-bottom: 2px;
  line-height: 1.5;
}
@media (max-width: 880px) {
  .logs-grid { grid-template-columns: 1fr; }
}
</style>
