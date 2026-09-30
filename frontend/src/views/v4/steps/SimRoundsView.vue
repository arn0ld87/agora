<script setup lang="ts">
/**
 * SimRoundsView — Runden-Ansicht (Kind-Route `rounds` von
 * SimulationLayout.vue). Slice UI-2b (#1713), Commit 4
 * (docs/design/simulation-feed.md §2.9).
 *
 * Mount-Logik (Stream + Snapshot) dupliziert bewusst das Muster aus
 * StepSimulationFeedView.vue/SimThreadsView.vue, damit SimRunHeader
 * (Runde/SimZeit/Beitragszahl) in allen vier Ansichten dieselbe Semantik
 * traegt — offener Punkt fuer die Design-Abnahme (siehe Bericht).
 *
 * Auswahl einer Runde schreibt `?round=` in die Query (router.replace) und
 * filtert damit auch Feed/Diskurs/Protokoll, ohne den Tab zu wechseln.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed } from '@/composables/useSimFeed'
import { getSimulationFeedSnapshot, getSimulationRounds } from '@/api/simulation'
import { unwrap } from '@/api/envelope'
import type { RoundSummary } from '@/contracts/simActionContract'
import SimRoundsList, { type SimRoundsListError } from '@/components/v4/sim-feed/SimRoundsList.vue'
import SimRunHeader, {
  type SimRunHeaderDegradation,
  type StreamState,
} from '@/components/v4/sim-feed/SimRunHeader.vue'

const route = useRoute()
const router = useRouter()
const simulationId = String(route.params.simulationId)
const feed = useSimFeed(simulationId)

const stream = useEventStream(simulationId, {
  post_created: (data) => feed.ingest(data),
})

const isSnapshotLoading = ref(true)
const snapshotFailedBoth = ref(false)
const streamStarted = ref(false)

const rounds = ref<RoundSummary[]>([])
const isRoundsLoading = ref(true)
const roundsError = ref<SimRoundsListError | null>(null)

async function loadSnapshot(): Promise<void> {
  isSnapshotLoading.value = true
  const [reddit, twitter] = await Promise.all([
    getSimulationFeedSnapshot(simulationId, 'reddit').catch(() => null),
    getSimulationFeedSnapshot(simulationId, 'twitter').catch(() => null),
  ])
  snapshotFailedBoth.value = reddit === null && twitter === null
  if (!snapshotFailedBoth.value) {
    feed.ingestMany([...(reddit ?? []), ...(twitter ?? [])])
  }
  isSnapshotLoading.value = false
}

async function loadRounds(): Promise<void> {
  isRoundsLoading.value = true
  roundsError.value = null
  try {
    const response = unwrap(await getSimulationRounds(simulationId))
    rounds.value = response.rounds ?? []
  } catch {
    roundsError.value = { code: 'rounds_failed', message: 'Runden konnten nicht geladen werden.' }
  } finally {
    isRoundsLoading.value = false
  }
}

onMounted(async () => {
  await stream.start()
  streamStarted.value = true
  await Promise.all([loadSnapshot(), loadRounds()])
})

onBeforeUnmount(() => {
  feed.flushPending()
  stream.stop()
})

const totalRounds = computed<number | null>(() => {
  if (rounds.value.length === 0) return null
  return Math.max(...rounds.value.map((r) => r.round_num)) + 1
})

const activeRound = computed<number | null>(() =>
  typeof route.query.round === 'string' && route.query.round !== '' ? Number(route.query.round) : null,
)

const currentRound = computed<number | null>(() => {
  if (activeRound.value !== null) return activeRound.value
  return totalRounds.value !== null ? totalRounds.value - 1 : null
})

const lastSimTime = computed<string | null>(() => {
  const items = feed.flatTimeline.value
  return items.length > 0 ? (items[items.length - 1].sim_time ?? items[items.length - 1].timestamp) : null
})

const streamState = computed<StreamState>(() => {
  if (!streamStarted.value) return 'connecting'
  if (stream.error.value) return 'reconnecting'
  if (stream.isStreaming.value) return 'open'
  return 'closed'
})

const isLegacyRun = computed(
  () => feed.flatTimeline.value.length > 0 && feed.flatTimeline.value.every((p) => p.kind == null),
)

const degradation = computed<SimRunHeaderDegradation | null>(() => {
  if (snapshotFailedBoth.value) {
    return { kind: 'snapshot_missing', hint: 'Anfangsbestand konnte nicht geladen werden.' }
  }
  if (streamState.value === 'reconnecting') {
    return { kind: 'stream_lost', hint: 'Live-Verbindung verloren.' }
  }
  if (isLegacyRun.value) {
    return { kind: 'legacy_run', hint: 'Aelterer Lauf ohne vollstaendige Diskurs-Daten.' }
  }
  return null
})

function selectRound(round: number): void {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (typeof value === 'string' && value.length > 0) next[key] = value
  }
  next.round = String(round)
  void router.replace({ query: next })
}
</script>

<template>
  <div class="srv-root">
    <SimRunHeader
      :simulation-id="simulationId"
      :current-round="currentRound"
      :total-rounds="totalRounds"
      :sim-time="lastSimTime"
      :post-count="feed.flatTimeline.value.length"
      :stream-state="streamState"
      :degradation="degradation"
      :loading="isSnapshotLoading"
    />
    <SimRoundsList
      :rounds="rounds"
      :active-round="activeRound"
      :stream-state="streamState"
      :loading="isRoundsLoading"
      :error="roundsError"
      @select="selectRound"
      @retry="loadRounds"
    />
  </div>
</template>

<style scoped>
.srv-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
</style>
