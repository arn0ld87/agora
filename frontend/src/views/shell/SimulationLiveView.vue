<script setup lang="ts">
/**
 * SimulationLiveView — Live-Instrument einer laufenden Simulation.
 *
 * Redesign PR 7 (Audit §5 "Simulation live", höchstes Risiko: Polling/
 * Events). Ersetzt den shell-losen, leeren Feed aus Step 3 durch ein
 * Vollbild-Instrument: Kopfzeile (Runde x/y, vergangene Zeit, s/Runde,
 * Fortsetzen/Abbrechen), Rundenachse, vier Bahnen (Akteure, Reddit,
 * Twitter, System/Ereignisse).
 *
 * Datenherkunft — ausschließlich bestehende Endpunkte, keine neuen:
 * - Runde x/y, Pause-Status: `getRunStatusDetail` (bestehender
 *   Simulation-Status-Endpunkt, api/simulation.ts) — dieselbe Quelle wie
 *   Step3Simulation.vue.
 * - vergangene Zeit und s/Runde: Wanduhr gegen `started_at`/`completed_at` aus
 *   dem Status-Detail-Payload. Bewusst NICHT die Sim-Uhr (`useSimClock`,
 *   abgeleitet aus `PostCreatedEvent.sim_time`): die zaehlt erst ab dem ersten
 *   Beitrag, den diese Sitzung selbst empfaengt, und zeigt nach einem Reload
 *   oder bei einem pausierten/ruhigen Lauf 00:00. Ausserdem ist "s/Runde" eine
 *   Durchsatzangabe — sie muss in echten Sekunden rechnen, nicht in simulierter
 *   Zeit.
 * - Akteure/Reddit/Twitter: `useSimFeed` + `useEventStream` (Zod-validierter
 *   PostCreatedEvent-Strom), wie StepSimulationFeedView.vue.
 * - System/Ereignisse: `getRunEvents` (`/api/runs/<id>/events`) und
 *   `getRunUsage` (`/api/runs/<id>/usage`). Die dafuer noetige RunRegistry-ID
 *   steht NICHT im Status-Detail-Payload — `SimulationRunState.to_dict()`
 *   (backend/app/services/sim/run_state_store.py) fuehrt kein `run_id`. Sie
 *   wird ueber `GET /api/runs?simulation_id=<id>` aufgeloest, den einzigen
 *   Vertrag, der diese Zuordnung tatsaechlich liefert.
 *
 * Bewusst weggelassen (siehe useDeriveSimulation.ts-Kommentar und PR-7-
 * Bericht): Rundenachse ohne Aktivitätshöhe pro Runde (PostCreatedEvent
 * trägt kein round_num), "Aufkommende Themen" (kein Themen-Endpunkt),
 * "Ereignis einspeisen"/"Budget anheben" (kein Eingriffs-Endpunkt gelistet).
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  getRunStatusDetail,
  pauseSimulation,
  resumeSimulation,
  getSimulationFeedSnapshot,
  type RunStatusResponse,
} from '@/api/simulation'
import { cancelRun, getRunEvents, listRuns } from '@/api/runs'
import { getRunUsage } from '@/api/budget'
import type { RunEvent } from '@/types/run'
import type { RunUsage } from '@/contracts/runBudgetContract'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed, clearSimFeed } from '@/composables/useSimFeed'
import { usePolling } from '@/composables/usePolling'
import {
  buildRoundTicks,
  buildActorStats,
  secondsPerRound,
  formatElapsed,
  formatSecondsPerRound,
} from '@/composables/useSimulationLiveMetrics'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import FeedColumn from '@/components/v4/sim-feed/FeedColumn.vue'
import RedditThread from '@/components/v4/sim-feed/RedditThread.vue'
import TwitterPost from '@/components/v4/sim-feed/TwitterPost.vue'
import Button from '@/components/v4/forms/Button.vue'
import { SimulationLiveTestId } from '@/contracts/testIds'

const { t } = useI18n()
const route = useRoute()
const simulationId = String(route.params.simulationId)

const feed = useSimFeed(simulationId)

const runStatus = ref<RunStatusResponse>({ simulation_id: simulationId, status: 'unknown' })
const runId = ref<string | null>(null)
const isPausing = ref(false)
const isCancelling = ref(false)
const events = ref<RunEvent[]>([])
const usage = ref<RunUsage | null>(null)
// Wanduhr-Anker: sekuendlich fortgeschrieben, damit `elapsedSeconds` bei einem
// laufenden Lauf weiterzaehlt, ohne dass ein Ereignis eintreffen muss.
const now = ref(Date.now())
let nowTimer: ReturnType<typeof setInterval> | null = null

const currentRound = computed(() => Number(runStatus.value.current_round ?? 0))
const totalRounds = computed(() => Number(runStatus.value.total_rounds ?? runStatus.value.max_rounds ?? 0))
const isPaused = computed(() => Boolean(runStatus.value.paused))

const roundTicks = computed(() => buildRoundTicks(currentRound.value, totalRounds.value))

function parseIsoMs(value: unknown): number | null {
  if (typeof value !== 'string' || value.length === 0) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

/**
 * Vergangene Zeit des Laufs in echten Sekunden. Anker ist `started_at` aus dem
 * persistierten Laufzustand, Endpunkt `completed_at` (abgeschlossener Lauf)
 * oder die Wanduhr (laufender Lauf). Damit stimmt die Anzeige auch nach einem
 * Reload und bei einem pausierten Lauf, der gerade keine Beitraege erzeugt.
 */
const elapsedSeconds = computed<number>(() => {
  const started = parseIsoMs(runStatus.value.started_at)
  if (started === null) return 0
  const ended = parseIsoMs(runStatus.value.completed_at) ?? now.value
  return Math.max(0, (ended - started) / 1000)
})

const elapsedDisplay = computed(() => formatElapsed(elapsedSeconds.value))
const secPerRoundDisplay = computed(() =>
  formatSecondsPerRound(secondsPerRound(elapsedSeconds.value, currentRound.value)),
)

// Chronologisch, nicht plattformweise: `twitterPosts` ist absteigend sortiert
// und `redditPosts` aufsteigend — eine blosse Verkettung ergaebe ein
// Reihenfolge-Kraut, und `buildActorStats` liest das Ende der Liste als
// juengstes Fenster.
const allPosts = computed(() =>
  [...feed.redditPosts.value, ...feed.twitterPosts.value].sort(
    (a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp),
  ),
)
const actorStats = computed(() => buildActorStats(allPosts.value))

const stream = useEventStream(simulationId, {
  state: (msg) => applyStatus(msg?.payload as Partial<RunStatusResponse> | undefined),
  control: (msg) => {
    const data = msg?.payload as { paused?: boolean } | undefined
    if (!data) return
    runStatus.value = { ...runStatus.value, paused: Boolean(data.paused) }
  },
  post_created: (data) => {
    if (!data) return
    feed.ingest(data)
  },
})

function applyStatus(data: Partial<RunStatusResponse> | undefined): void {
  if (!data || typeof data !== 'object') return
  runStatus.value = { ...runStatus.value, ...data }
}

async function pollStatus(): Promise<void> {
  try {
    const res = await getRunStatusDetail(simulationId)
    if (res?.success) applyStatus(res.data)
  } catch {
    // Polling-Fehler sind transient — nächster Tick versucht es erneut.
  }
}

const statusPolling = usePolling(pollStatus, 2500)

/**
 * Loest die RunRegistry-ID zu dieser Simulation auf und merkt sie sich.
 *
 * `GET /api/runs?simulation_id=<id>` ist der einzige Vertrag, der die Zuordnung
 * Simulation → Lauf liefert; die Liste ist absteigend nach `updated_at`
 * sortiert (run_registry.list_runs), der erste Treffer ist also der aktuelle
 * Lauf. Solange noch kein Lauf registriert ist, bleibt der Rueckgabewert `null`
 * und der naechste Tick versucht es erneut.
 */
async function resolveRunId(): Promise<string | null> {
  if (runId.value) return runId.value
  try {
    const res = await listRuns({ simulation_id: simulationId, limit: 1 })
    const first = res?.data?.runs?.[0]
    if (first?.run_id) runId.value = first.run_id
  } catch {
    // Ohne Registry-ID bleibt nur die System-Bahn leer; das Instrument laeuft weiter.
  }
  return runId.value
}

async function pollSystemLane(): Promise<void> {
  const id = await resolveRunId()
  if (!id) return
  try {
    const [eventsRes, usageRes] = await Promise.all([
      getRunEvents(id).catch(() => null),
      getRunUsage(id).catch(() => null),
    ])
    if (eventsRes?.success && Array.isArray(eventsRes.data)) events.value = eventsRes.data
    if (usageRes?.success && usageRes.data) usage.value = usageRes.data
  } catch {
    // Systemwerte sind ergänzend — ein Fehlschlag blockiert das Instrument nicht.
  }
}

const systemPolling = usePolling(pollSystemLane, 5000)

async function doPauseResume(): Promise<void> {
  isPausing.value = true
  try {
    const res = isPaused.value
      ? await resumeSimulation(simulationId)
      : await pauseSimulation(simulationId)
    if (res?.success) runStatus.value = { ...runStatus.value, paused: !isPaused.value }
  } finally {
    isPausing.value = false
  }
}

async function doCancel(): Promise<void> {
  isCancelling.value = true
  try {
    await cancelRun(simulationId)
  } finally {
    isCancelling.value = false
  }
}

onMounted(async () => {
  nowTimer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
  await stream.start()
  // Erster Status-Poll wird bewusst abgewartet: die Kopfzeile (Runde, vergangene
  // Zeit) haengt vollstaendig an ihm, und ohne den Await stuende sie bis zum
  // ersten Intervall-Tick auf Nullwerten.
  await pollStatus()
  void statusPolling.start({ immediate: false })
  void systemPolling.start({ immediate: true })
  try {
    const [reddit, twitter] = await Promise.all([
      getSimulationFeedSnapshot(simulationId, 'reddit').catch(() => []),
      getSimulationFeedSnapshot(simulationId, 'twitter').catch(() => []),
    ])
    feed.ingestMany([...reddit, ...twitter])
  } catch {
    // Snapshot ist ergänzend zum Live-Strom — ein Fehlschlag lässt den
    // Stream unangetastet (analog StepSimulationFeedView.vue).
  }
})

onBeforeUnmount(() => {
  feed.flushPending()
  stream.stop()
  statusPolling.stop()
  systemPolling.stop()
  if (nowTimer !== null) {
    clearInterval(nowTimer)
    nowTimer = null
  }
  clearSimFeed(simulationId)
})
</script>

<template>
  <AppShell>
    <PageHeader :title="t('step3.live.title')" />
    <div class="sl-root" :data-testid="SimulationLiveTestId.root">
      <header class="sl-header" role="status" :aria-label="t('step3.live.title')">
        <div class="sl-header-metric" :data-testid="SimulationLiveTestId.headerRound">
          <span class="sl-metric-value">{{ currentRound }}<span class="sl-metric-dim">/{{ totalRounds }}</span></span>
          <span class="sl-metric-label">{{ t('step3.live.round') }}</span>
        </div>
        <div class="sl-header-metric" :data-testid="SimulationLiveTestId.headerElapsed">
          <span class="sl-metric-value">{{ elapsedDisplay }}</span>
          <span class="sl-metric-label">{{ t('step3.live.elapsed') }}</span>
        </div>
        <div class="sl-header-metric" :data-testid="SimulationLiveTestId.headerSecPerRound">
          <span class="sl-metric-value">{{ secPerRoundDisplay }}</span>
          <span class="sl-metric-label">{{ t('step3.live.secPerRound') }}</span>
        </div>
        <span class="sl-header-spacer"></span>
        <Button
          variant="secondary"
          size="sm"
          :loading="isPausing"
          :data-testid="SimulationLiveTestId.headerPauseResume"
          @click="doPauseResume"
        >
          {{ isPaused ? t('step3.controls.resume') : t('step3.controls.pause') }}
        </Button>
        <Button
          variant="danger"
          size="sm"
          :loading="isCancelling"
          :data-testid="SimulationLiveTestId.headerCancel"
          @click="doCancel"
        >
          {{ t('step3.controls.cancel') }}
        </Button>
      </header>

      <nav
        class="sl-axis"
        :aria-label="t('step3.live.roundAxis')"
        :data-testid="SimulationLiveTestId.roundAxis"
      >
        <span class="sl-axis-label">{{ t('step3.live.roundAxisHint') }}</span>
        <ol class="sl-axis-ticks">
          <li
            v-for="tick in roundTicks"
            :key="tick.round"
            class="sl-tick"
            :class="`sl-tick--${tick.state}`"
            :aria-current="tick.state === 'now' ? 'step' : undefined"
            :data-testid="SimulationLiveTestId.roundTick"
            :title="`${t('step3.live.round')} ${tick.round}`"
          ></li>
        </ol>
      </nav>

      <div class="sl-lanes">
        <section
          class="sl-lane"
          :aria-label="t('step3.live.lanes.actors')"
          :data-testid="SimulationLiveTestId.laneActors"
        >
          <header class="sl-lane-head">
            <span>{{ t('step3.live.lanes.actors') }}</span>
            <span class="sl-lane-count">{{ t('step3.live.actorsActive', { count: actorStats.length }) }}</span>
          </header>
          <ul class="sl-actor-list">
            <li
              v-for="actor in actorStats"
              :key="actor.personaId"
              class="sl-actor-row"
              :class="{ 'sl-actor-row--active': actor.isActive }"
              tabindex="0"
              :data-testid="SimulationLiveTestId.actorRow"
            >
              <span class="sl-actor-name">{{ actor.personaName }}</span>
              <span class="sl-actor-count">{{ actor.count }}</span>
            </li>
          </ul>
          <p v-if="actorStats.length === 0" class="sl-empty">{{ t('step3.live.empty') }}</p>
        </section>

        <div :data-testid="SimulationLiveTestId.laneReddit">
          <FeedColumn
            :title="t('step3.live.lanes.reddit')"
            channel="reddit"
            :has-items="feed.redditPosts.value.length > 0"
          >
            <TransitionGroup name="sl-slide-in" tag="div" class="sl-thread-list">
              <RedditThread
                v-for="node in feed.redditTree.value"
                :key="node.post_id"
                :node="node"
              />
            </TransitionGroup>
            <p v-if="feed.redditPosts.value.length === 0" class="sl-empty">{{ t('step3.live.empty') }}</p>
          </FeedColumn>
        </div>

        <div :data-testid="SimulationLiveTestId.laneTwitter">
          <FeedColumn
            :title="t('step3.live.lanes.twitter')"
            channel="twitter"
            :has-items="feed.twitterPosts.value.length > 0"
          >
            <TransitionGroup name="sl-slide-in" tag="div" class="sl-post-list">
              <TwitterPost
                v-for="post in feed.twitterPosts.value"
                :key="post.post_id"
                :post="post"
              />
            </TransitionGroup>
            <p v-if="feed.twitterPosts.value.length === 0" class="sl-empty">{{ t('step3.live.empty') }}</p>
          </FeedColumn>
        </div>

        <aside
          class="sl-lane"
          :aria-label="t('step3.live.lanes.system')"
          :data-testid="SimulationLiveTestId.laneSystem"
        >
          <header class="sl-lane-head">
            <span>{{ t('step3.live.lanes.system') }}</span>
          </header>
          <dl v-if="usage" class="sl-kv-list">
            <div class="sl-kv-row">
              <dt>{{ t('step3.live.usage.llmCalls') }}</dt>
              <dd>{{ usage.totals.llm_calls }}</dd>
            </div>
            <div v-if="usage.totals.total_tokens != null" class="sl-kv-row">
              <dt>{{ t('step3.live.usage.tokens') }}</dt>
              <dd>{{ usage.totals.total_tokens }}</dd>
            </div>
          </dl>
          <div class="sl-events">
            <span class="sl-lane-count">{{ t('step3.live.events.title') }}</span>
            <ul class="sl-event-list">
              <li
                v-for="(event, idx) in events"
                :key="`${event.timestamp}-${idx}`"
                class="sl-event-row"
                :data-testid="SimulationLiveTestId.eventRow"
              >
                <span class="sl-event-type">{{ event.type }}</span>
                <span v-if="event.message" class="sl-event-message">{{ event.message }}</span>
              </li>
            </ul>
            <p v-if="events.length === 0" class="sl-empty">{{ t('step3.live.events.empty') }}</p>
          </div>
        </aside>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.sl-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.sl-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--hairline);
}
.sl-header-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sl-metric-value {
  font-family: var(--font-mono, monospace);
  font-size: 20px;
  color: var(--text-primary);
}
.sl-metric-dim {
  color: var(--text-secondary);
  font-size: 14px;
}
.sl-metric-label {
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
}
.sl-header-spacer {
  flex: 1;
}
.sl-axis {
  padding: 10px 24px;
  border-bottom: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sl-axis-label {
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
}
.sl-axis-ticks {
  display: flex;
  gap: 4px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.sl-tick {
  flex: 1;
  height: 12px;
  border-radius: 2px;
  background: var(--hairline);
}
.sl-tick--done {
  background: var(--text-secondary);
}
.sl-tick--now {
  background: var(--accent-live);
}
.sl-tick--todo {
  background: transparent;
  border: 1px dashed var(--hairline);
}
.sl-lanes {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr) minmax(0, 1fr) 300px;
  gap: 0;
}
.sl-lane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  border-right: 1px solid var(--hairline);
}
.sl-lane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hairline);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
}
.sl-lane-count {
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary);
}
.sl-actor-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.sl-actor-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 16px;
  border-top: 1px solid var(--hairline);
}
.sl-actor-row:focus-visible {
  outline: 2px solid var(--accent-live);
  outline-offset: -2px;
}
.sl-actor-row--active {
  /* Live-Tint, nicht der Kupfer-Akzent: eine aktive Akteurszeile ist ein
     "jetzt"-Zustand, und Kupfer bleibt laut Audit §3 der Primaeraktion und
     der Selektion vorbehalten. */
  background: var(--accent-live-soft);
}
.sl-actor-count {
  font-family: var(--font-mono, monospace);
  color: var(--text-secondary);
}
.sl-thread-list,
.sl-post-list {
  display: flex;
  flex-direction: column;
}
.sl-kv-list {
  margin: 0;
  padding: 12px 16px;
  border-bottom: 1px solid var(--hairline);
}
.sl-kv-row {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono, monospace);
  font-size: 11.5px;
  color: var(--text-secondary);
  padding: 3px 0;
}
.sl-events {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sl-event-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sl-event-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}
.sl-event-type {
  font-family: var(--font-mono, monospace);
  color: var(--text-faint);
}
.sl-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* Fortschritt/Live-Punkt sind die einzigen erlaubten Daueranimationen; die
   Slide-in-Übergänge hier sind Enter-Transitions (keine Dauerschleife) und
   liegen NICHT auf Fokus-Eigenschaften (outline/box-shadow/border-color) —
   der Playwright-Fokus-Check misst also keine laufende Transition. */
.sl-slide-in-enter-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.sl-slide-in-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.sl-slide-in-leave-active {
  display: none;
}
@media (prefers-reduced-motion: reduce) {
  .sl-slide-in-enter-active {
    transition: none;
  }
}

@media (max-width: 1279px) {
  .sl-lanes {
    grid-template-columns: 200px minmax(0, 1fr) 280px;
  }
  .sl-lane:nth-child(3) {
    display: none;
  }
}
</style>
