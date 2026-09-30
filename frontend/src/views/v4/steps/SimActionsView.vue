<script setup lang="ts">
/**
 * SimActionsView — Protokoll (Kind-Route `actions` von SimulationLayout.vue).
 * Slice UI-2b (#1713), Commit 5 (docs/design/simulation-feed.md §2.10).
 *
 * Deviation: die Aktionsart (`?type=`) ist in KEINEM der beiden §2-Vertraege
 * (SimFilterBarProps §2.2, SimActionsTableProps §2.10) als Steuerungs-Prop
 * vorgesehen, obwohl §1 sie explizit als View-Query fuer `actions` listet.
 * SimFilterBar bleibt darum unveraendert (kein ungefragter Refactor an
 * bereits abgenommenem Code); diese View ergaenzt ein eigenes, kleines
 * Aktionsart-Select im selben Token-Stil direkt neben der Filterleiste.
 *
 * Mount-Logik (Stream + Snapshot fuer Persona-Optionen und SimRunHeader)
 * dupliziert bewusst das Muster der Geschwister-Views — offener Punkt fuer
 * die Design-Abnahme (siehe Bericht).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed } from '@/composables/useSimFeed'
import { getSimulationFeedSnapshot, getSimulationActions, getSimulationRounds } from '@/api/simulation'
import { unwrap } from '@/api/envelope'
import type { Platform } from '@/contracts/postEventContract'
import type { SimActionPage, SimActionType } from '@/contracts/simActionContract'
import SimActionsTable from '@/components/v4/sim-feed/SimActionsTable.vue'
import SimFilterBar from '@/components/v4/sim-feed/SimFilterBar.vue'
import SimRunHeader, {
  type SimRunHeaderDegradation,
  type StreamState,
} from '@/components/v4/sim-feed/SimRunHeader.vue'

const ACTION_TYPES: SimActionType[] = [
  'CREATE_POST',
  'CREATE_COMMENT',
  'REPOST',
  'QUOTE_POST',
  'LIKE_POST',
  'LIKE_COMMENT',
  'DISLIKE_POST',
  'DISLIKE_COMMENT',
  'FOLLOW',
  'MUTE',
  'SEARCH_POSTS',
  'SEARCH_USER',
  'TREND',
  'REFRESH',
  'INTERVIEW',
  'DO_NOTHING',
  'OTHER',
]

const route = useRoute()
const router = useRouter()
const simulationId = String(route.params.simulationId)
const feed = useSimFeed(simulationId)
const { t } = useI18n()

const stream = useEventStream(simulationId, {
  post_created: (data) => feed.ingest(data),
})

const isSnapshotLoading = ref(true)
const snapshotFailedBoth = ref(false)
const streamStarted = ref(false)

const page = ref<SimActionPage>({ items: [], next_cursor: null })
const isActionsLoading = ref(true)
const actionsError = ref<{ code: string; message: string } | null>(null)

const platformFilter = computed<'all' | Platform>(
  () => (route.query.platform as 'all' | Platform) ?? 'all',
)
const roundFilter = computed<number | null>(() =>
  typeof route.query.round === 'string' && route.query.round !== '' ? Number(route.query.round) : null,
)
const personaFilter = computed<string | null>(
  () => (typeof route.query.persona === 'string' ? route.query.persona : null) || null,
)
const typeFilter = computed<SimActionType | null>(() => {
  const raw = route.query.type
  return typeof raw === 'string' && ACTION_TYPES.includes(raw as SimActionType) ? (raw as SimActionType) : null
})
// `since` (§1): GET /actions kennt den Parameter serverseitig nicht (siehe
// backend/app/api/simulation_run.py::get_simulation_actions — nur limit,
// cursor, platform, agent_id, round_num, action_type). Darum clientseitig
// gegen `timestamp` gefiltert, nachdem eine Seite geladen wurde; die
// Cursor-Pagination selbst bleibt unangetastet (loadMore laeuft ungefiltert
// weiter, nur die Anzeige wird eingeschraenkt).
const sinceFilter = computed<string | null>(
  () => (typeof route.query.since === 'string' ? route.query.since : null) || null,
)
const filteredActionItems = computed(() =>
  sinceFilter.value === null
    ? page.value.items
    : page.value.items.filter((action) => action.timestamp >= sinceFilter.value!),
)

function updateQuery(patch: Record<string, string | null>): void {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries({ ...route.query, ...patch })) {
    if (typeof value === 'string' && value.length > 0) next[key] = value
  }
  void router.replace({ query: next })
}

function onTypeChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  updateQuery({ type: value.length > 0 ? value : null })
}

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

async function loadActions(reset: boolean): Promise<void> {
  isActionsLoading.value = true
  actionsError.value = null
  try {
    const response = unwrap(
      await getSimulationActions(simulationId, {
        cursor: reset ? undefined : (page.value.next_cursor ?? undefined),
        round_num: roundFilter.value ?? undefined,
        agent_id: personaFilter.value ?? undefined,
        platform: platformFilter.value === 'all' ? undefined : platformFilter.value,
        action_type: typeFilter.value ?? undefined,
      }),
    )
    page.value = reset
      ? response
      : { items: [...page.value.items, ...response.items], next_cursor: response.next_cursor }
  } catch {
    actionsError.value = { code: 'actions_failed', message: t('feed.actionsTable.loadError') }
  } finally {
    isActionsLoading.value = false
  }
}

onMounted(async () => {
  await stream.start()
  streamStarted.value = true
  await Promise.all([loadSnapshot(), loadActions(true)])
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

// Filter-Aenderung laedt das Protokoll neu (Cursor zurueckgesetzt), statt an
// die alte Seite anzuhaengen.
watch([roundFilter, platformFilter, personaFilter, typeFilter], () => {
  void loadActions(true)
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

const totalRounds = ref<number | null>(null)

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

function openPost(postId: string): void {
  void router.push({ name: 'SimThreadFocus', params: { simulationId, postId }, query: route.query })
}
</script>

<template>
  <div class="sav-root">
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
    <div class="sav-filters">
      <SimFilterBar
        scope="actions"
        :platform="platformFilter"
        :round="roundFilter"
        :persona="personaFilter"
        q=""
        :personas="personaOptions"
        :rounds="roundOptions"
        :loading="isSnapshotLoading"
        @update:platform="(v) => updateQuery({ platform: v === 'all' ? null : v })"
        @update:round="(v) => updateQuery({ round: v === null ? null : String(v) })"
        @update:persona="(v) => updateQuery({ persona: v })"
        @update:q="() => {}"
      />
      <div class="sav-type-field">
        <label class="sav-type-label" for="sav-type">{{ t('feed.actionsTable.type') }}</label>
        <select id="sav-type" class="sav-type-select" :value="typeFilter ?? ''" @change="onTypeChange">
          <option value="">{{ t('feed.scope.platformAll') }}</option>
          <option v-for="type in ACTION_TYPES" :key="type" :value="type">
            {{ t(`feed.actionType.${type}`) }}
          </option>
        </select>
      </div>
    </div>
    <SimActionsTable
      :page="{ items: filteredActionItems, next_cursor: page.next_cursor }"
      :loading="isActionsLoading"
      :filters="{
        round: roundFilter ?? undefined,
        agentId: personaFilter ?? undefined,
        platform: platformFilter === 'all' ? undefined : platformFilter,
        actionType: typeFilter ?? undefined,
      }"
      @load-more="() => loadActions(false)"
      @open-post="openPost"
    />
    <p v-if="actionsError" class="sav-error" role="alert">{{ actionsError.message }}</p>
  </div>
</template>

<style scoped>
.sav-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.sav-filters {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
}
.sav-type-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 160px;
  padding: var(--sim-header-py) var(--sim-header-px);
  border-bottom: 1px solid var(--hairline);
}
.sav-type-label {
  font-size: 11.5px;
  font-weight: 590;
  color: var(--text-secondary);
}
.sav-type-select {
  height: var(--ctl-h-md, 34px);
  padding: 0 10px;
  background: var(--surface-inset);
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  color: var(--text-primary);
  font-size: var(--sim-time-fs);
}
.sav-error {
  margin: 0;
  padding: 8px var(--sim-header-px);
  text-align: center;
  font-size: var(--sim-time-fs);
  color: var(--status-red);
}
</style>
