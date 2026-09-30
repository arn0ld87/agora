<script setup lang="ts">
/**
 * StepSimulationFeedView — kanonischer Feed als chronologische Timeline.
 *
 * Slice UI-2b (#1713), Commit 3 (docs/design/simulation-feed.md §2.5, §5).
 * Ersetzt die Dual-Column-Ansicht (Reddit-Baum + Twitter-Flow) durch eine
 * gemeinsame virtualisierte Timeline mit Filterleiste und Statusstreifen.
 *
 * useEventStream-API: handlers werden im Constructor uebergeben, kein .on().
 * post_created routet direkt in useSimFeed.ingest().
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed } from '@/composables/useSimFeed'
import { getSimulationFeedSnapshot, getSimulationRounds } from '@/api/simulation'
import { unwrap } from '@/api/envelope'
import type { Platform } from '@/contracts/postEventContract'
import FeedTimeline from '@/components/v4/sim-feed/FeedTimeline.vue'
import SimFilterBar from '@/components/v4/sim-feed/SimFilterBar.vue'
import SimRunHeader, {
  type SimRunHeaderDegradation,
  type StreamState,
} from '@/components/v4/sim-feed/SimRunHeader.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const simulationId = String(route.params.simulationId)
const feed = useSimFeed(simulationId)

const stream = useEventStream(simulationId, {
  post_created: (data) => feed.ingest(data),
})

const isSnapshotLoading = ref(true)
const snapshotError = ref<{ code: string; message: string } | null>(null)
const snapshotFailedBoth = ref(false)
const totalRounds = ref<number | null>(null)
const streamStarted = ref(false)

// --- Query-Filter (persistiert via URL, §1) -------------------------------

const platformFilter = computed<'all' | Platform>(
  () => (route.query.platform as 'all' | Platform) ?? 'all',
)
const roundFilter = computed<number | null>(() =>
  typeof route.query.round === 'string' && route.query.round !== ''
    ? Number(route.query.round)
    : null,
)
const personaFilter = computed<string | null>(
  () => (typeof route.query.persona === 'string' ? route.query.persona : null) || null,
)
const qFilter = computed<string>(() => (typeof route.query.q === 'string' ? route.query.q : ''))
// `since` (§1): Backend kennt den Parameter weder fuer /feed-snapshot noch
// fuer den Stream, darum rein clientseitig gegen `timestamp` gefiltert
// (Wandzeit des Events, nicht `sim_time` — die ist optional/nullable und
// nicht fuer jeden Altlauf gesetzt). Persistenz laeuft ueber updateQuery,
// die bestehende Query-Parameter unveraendert mitfuehrt.
const sinceFilter = computed<string | null>(
  () => (typeof route.query.since === 'string' ? route.query.since : null) || null,
)

function updateQuery(patch: Record<string, string | null>): void {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries({ ...route.query, ...patch })) {
    if (typeof value === 'string' && value.length > 0) next[key] = value
  }
  void router.replace({ query: next })
}

async function loadSnapshot(): Promise<void> {
  isSnapshotLoading.value = true
  snapshotError.value = null
  const [reddit, twitter] = await Promise.all([
    getSimulationFeedSnapshot(simulationId, 'reddit').catch(() => null),
    getSimulationFeedSnapshot(simulationId, 'twitter').catch(() => null),
  ])
  snapshotFailedBoth.value = reddit === null && twitter === null
  if (snapshotFailedBoth.value) {
    snapshotError.value = { code: 'snapshot_failed', message: t('feed.errors.snapshotFailed') }
  } else {
    feed.ingestMany([...(reddit ?? []), ...(twitter ?? [])])
  }
  isSnapshotLoading.value = false
}

onMounted(async () => {
  // #1009 — Stream zuerst starten, danach den Snapshot mergen; seen-Dedup
  // faengt den Overlap ab (siehe useSimFeed).
  await stream.start()
  streamStarted.value = true
  await loadSnapshot()
  try {
    const rounds = unwrap(await getSimulationRounds(simulationId))
    const list = rounds.rounds ?? []
    totalRounds.value = list.length > 0 ? Math.max(...list.map((r) => r.round_num)) + 1 : null
  } catch {
    totalRounds.value = null
  }
})

onBeforeUnmount(() => {
  feed.flushPending()
  stream.stop()
})

// --- Gefilterte, sortierte Liste ------------------------------------------

const filteredItems = computed(() => {
  const q = qFilter.value.trim().toLowerCase()
  return feed.flatTimeline.value.filter((post) => {
    if (platformFilter.value !== 'all' && post.platform !== platformFilter.value) return false
    if (roundFilter.value !== null && post.round_num !== roundFilter.value) return false
    if (personaFilter.value !== null && post.persona_id !== personaFilter.value) return false
    if (sinceFilter.value !== null && post.timestamp < sinceFilter.value) return false
    if (q.length > 0 && !post.body.toLowerCase().includes(q)) return false
    return true
  })
})

const personaOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const post of feed.flatTimeline.value) {
    if (!seen.has(post.persona_id)) seen.set(post.persona_id, post.persona_name)
  }
  return [...seen.entries()].map(([id, name]) => ({ id, name }))
})

const roundOptions = computed(() => {
  const rounds = new Set<number>()
  for (const post of feed.flatTimeline.value) {
    if (typeof post.round_num === 'number') rounds.add(post.round_num)
  }
  return [...rounds].sort((a, b) => a - b)
})

const currentRound = computed<number | null>(() => {
  const rounds = roundOptions.value
  return rounds.length > 0 ? rounds[rounds.length - 1] : null
})

const lastSimTime = computed<string | null>(() => {
  const items = feed.flatTimeline.value
  return items.length > 0 ? (items[items.length - 1].sim_time ?? items[items.length - 1].timestamp) : null
})

// --- Statusstreifen ---------------------------------------------------

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

function openThread(postId: string): void {
  void router.push({
    name: 'SimThreadFocus',
    params: { simulationId, postId },
    query: route.query,
  })
}
</script>

<template>
  <div class="sf-root">
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
    <SimFilterBar
      scope="feed"
      :platform="platformFilter"
      :round="roundFilter"
      :persona="personaFilter"
      :q="qFilter"
      :personas="personaOptions"
      :rounds="roundOptions"
      :loading="isSnapshotLoading"
      @update:platform="(v) => updateQuery({ platform: v === 'all' ? null : v })"
      @update:round="(v) => updateQuery({ round: v === null ? null : String(v) })"
      @update:persona="(v) => updateQuery({ persona: v })"
      @update:q="(v) => updateQuery({ q: v.length > 0 ? v : null })"
    />
    <FeedTimeline
      :items="filteredItems"
      :stream-state="streamState"
      :is-snapshot-loading="isSnapshotLoading"
      :error="snapshotError"
      @open-thread="openThread"
      @retry="loadSnapshot"
    />
  </div>
</template>

<style scoped>
.sf-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
</style>
