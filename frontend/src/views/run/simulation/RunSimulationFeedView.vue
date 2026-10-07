<script setup lang="ts">
/**
 * Feed der Simulation am Lauf (Etappe 4, #1801, Bauplan 4.5): Dreispalter mit
 * Netzwerk-Umschalter und Filtern links, Zeitleiste in der Mitte und
 * Persona-Karte samt „Runde x von y" rechts. Netzwerk steht in der Adresse
 * (`…/feed/:network?`, Standard Twitter), Filter in der Query (`persona`,
 * `round`, `q`). Die Überschrift gehört dem Arbeitsbereich: kein `h1` hier.
 */
import { computed, inject, ref, toRef } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import FeedNotices from '@/components/run/simulation/FeedNotices.vue'
import FeedSidebar from '@/components/run/simulation/FeedSidebar.vue'
import PersonaCard from '@/components/run/simulation/PersonaCard.vue'
import RedditRow from '@/components/run/simulation/RedditRow.vue'
import RoundPanel from '@/components/run/simulation/RoundPanel.vue'
import RoundScrubber from '@/components/run/simulation/RoundScrubber.vue'
import RunSimEmptyState from '@/components/run/simulation/RunSimEmptyState.vue'
import TwitterCard from '@/components/run/simulation/TwitterCard.vue'
import { FEED_SNAPSHOT_LIMIT, useRunFeed } from '@/composables/run/simulation/useRunFeed'
import { useRunPersonas } from '@/composables/run/simulation/useRunPersonas'
import { usePersonasReady } from '@/composables/run/simulation/usePersonasReady'
import { useSimulationRunStateContext } from '@/composables/run/simulation/useSimulationRunStateContext'
import {
  buildRedditList,
  buildTwitterTimeline,
  countUnrounded,
  filterPosts,
  type FeedNetwork,
  type FeedPost,
} from '@/composables/run/simulation/threads'
import { NOT_FINISHED_STATES } from '@/composables/run/runStageState'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'

const props = defineProps<{ simulationId: string; network?: string }>()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const workspace = inject(RUN_WORKSPACE_KEY, null)
const personasReady = usePersonasReady()

const idRef = toRef(props, 'simulationId')
const feed = useRunFeed(idRef)
const personas = useRunPersonas(idRef)
const runState = useSimulationRunStateContext(() => props.simulationId)

const network = computed<FeedNetwork>(() => (props.network === 'reddit' ? 'reddit' : 'twitter'))

// --- Filter aus der Query ---------------------------------------------------

function queryString(key: string): string {
  const raw = route.query[key]
  const value = Array.isArray(raw) ? raw[0] : raw
  return typeof value === 'string' ? value : ''
}
const personaFilter = computed(() => queryString('persona'))
const queryFilter = computed(() => queryString('q'))
const roundFilter = computed<number | null>(() => {
  const n = Number(queryString('round'))
  return queryString('round') !== '' && Number.isInteger(n) ? n : null
})

function setQuery(patch: Record<string, string | null>): void {
  const next: LocationQueryRaw = { ...route.query }
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === '') delete next[key]
    else next[key] = value
  }
  void router.replace({ query: next })
}
function setNetwork(next: FeedNetwork): void {
  if (next === network.value && props.network === next) return
  void router.push({
    name: 'RunSimulationFeed',
    params: { simulationId: props.simulationId, network: next },
    query: route.query,
  })
}
function resetFilters(): void {
  setQuery({ persona: null, round: null, q: null })
}
function postTo(postId: string) {
  return {
    name: 'RunSimulationPost',
    params: { simulationId: props.simulationId, postId },
    query: route.query,
  }
}
function openPost(postId: string): void {
  void router.push(postTo(postId))
}

// --- Daten für das gewählte Netzwerk ----------------------------------------

const networkPosts = computed(() => filterPosts(feed.visiblePosts.value, { network: network.value }))
const filter = computed(() => ({
  personaId: personaFilter.value,
  round: roundFilter.value,
  query: queryFilter.value,
}))
const filtersActive = computed(
  () => personaFilter.value !== '' || roundFilter.value !== null || queryFilter.value.trim() !== '',
)

/** Zähler und Fäden entstehen aus dem ganzen Netzwerk; gefiltert wird erst die Anzeige. */
function keepIds(posts: FeedPost[]): Set<string> {
  return new Set(filterPosts(posts, filter.value).map((p) => p.post_id))
}

const twitterEntries = computed(() => {
  if (network.value !== 'twitter') return []
  const timeline = buildTwitterTimeline(networkPosts.value)
  const keep = keepIds(timeline.map((e) => e.post))
  return timeline.filter((e) => keep.has(e.post.post_id)).reverse()
})
const redditEntries = computed(() => {
  if (network.value !== 'reddit') return []
  const list = buildRedditList(networkPosts.value)
  const keep = keepIds(list.map((e) => e.post))
  return list.filter((e) => keep.has(e.post.post_id)).reverse()
})
const entryCount = computed(() => twitterEntries.value.length + redditEntries.value.length)

const allNetworkPosts = computed(() => filterPosts(feed.posts.value, { network: network.value }))
const personaOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const p of allNetworkPosts.value) if (!seen.has(p.persona_id)) seen.set(p.persona_id, p.persona_name)
  return [...seen.entries()].map(([id, name]) => ({ id, name }))
})
const roundOptions = computed(() => {
  const rounds = new Set<number>()
  for (const p of allNetworkPosts.value) if (typeof p.round_num === 'number') rounds.add(p.round_num)
  return [...rounds].sort((a, b) => a - b)
})

// --- Rundenregler, Persona und Runde rechts ---------------------------------

const maxRound = computed(() => feed.maxRoundSeen.value ?? runState.currentRound.value)
const unrounded = computed(() => (feed.roundCursor.value === null ? 0 : countUnrounded(feed.posts.value)))
const panelRound = computed(() => feed.roundCursor.value ?? maxRound.value)
const activity = computed(() => {
  const round = panelRound.value
  const counts = { twitter: 0, reddit: 0 }
  if (round === null) return counts
  for (const p of feed.posts.value) if (p.round_num === round) counts[p.platform] += 1
  return counts
})

const focusedPersonaId = ref<string | null>(null)
const selectedPersonaId = computed(() => focusedPersonaId.value ?? (personaFilter.value || null))
const selectedPersona = computed(() =>
  selectedPersonaId.value ? personas.personaById(selectedPersonaId.value) : null,
)
const fallbackName = computed(() => {
  const id = selectedPersonaId.value
  if (!id) return null
  return personaOptions.value.find((p) => p.id === id)?.name ?? null
})

// „Befragen": nur bei gewählter Persona und abgeschlossener Simulation (Etappe 6).
const interviewTo = computed(() =>
  selectedPersonaId.value && !NOT_FINISHED_STATES.has(runState.stateKind.value)
    ? {
        name: 'RunInterviews',
        params: { simulationId: props.simulationId, conversationId: `persona-${selectedPersonaId.value}` },
      }
    : null,
)

// --- Zustände ---------------------------------------------------------------

const notStarted = computed(() => runState.stateKind.value === 'notStarted')
const loadingInitial = computed(() => feed.loading.value && feed.posts.value.length === 0)
const streamError = computed(() => feed.streamState.value === 'error')

async function onStarted(runId: string | null): Promise<void> {
  await runState.adoptRunId(runId)
  await feed.reload()
  await workspace?.reload()
}

const leftOpen = ref(false)
const rightOpen = ref(false)
</script>

<template>
  <div class="feed" data-testid="run-sim-feed">
    <RunSimEmptyState
      v-if="notStarted"
      :simulation-id="simulationId"
      :personas-ready="personasReady"
      @started="onStarted"
    />

    <template v-else>
      <RoundScrubber
        :cursor="feed.roundCursor.value"
        :max-round="maxRound"
        :pending-count="feed.pendingCount.value"
        @update:cursor="feed.setRoundCursor"
        @flush="feed.flushPending"
      />

      <FeedNotices
        :error="feed.error.value"
        :truncated="feed.truncated.value"
        :limit="FEED_SNAPSHOT_LIMIT"
        :invalid-count="feed.invalidCount.value"
        :evicted-count="feed.evictedCount.value"
        :unrounded-count="unrounded"
        :stream-error="streamError"
        @reload="feed.reload"
      />

      <div class="feed__toggles">
        <button
          type="button"
          class="feed__toggle"
          :aria-expanded="leftOpen"
          aria-controls="feed-left"
          data-testid="feed-toggle-left"
          @click="leftOpen = !leftOpen"
        >
          {{ leftOpen ? t('views.run.simFeed.toggle.hideFilters') : t('views.run.simFeed.toggle.showFilters') }}
        </button>
        <button
          type="button"
          class="feed__toggle"
          :aria-expanded="rightOpen"
          aria-controls="feed-right"
          data-testid="feed-toggle-right"
          @click="rightOpen = !rightOpen"
        >
          {{ rightOpen ? t('views.run.simFeed.toggle.hideSide') : t('views.run.simFeed.toggle.showSide') }}
        </button>
      </div>

      <div class="feed__grid">
        <aside id="feed-left" class="feed__aside" :class="{ 'feed__aside--collapsed': !leftOpen }">
          <FeedSidebar
            :network="network"
            :persona="personaFilter"
            :round="roundFilter"
            :query="queryFilter"
            :persona-options="personaOptions"
            :round-options="roundOptions"
            :contested-question="personas.contestedQuestion.value"
            @update:network="setNetwork"
            @update:persona="(v: string) => setQuery({ persona: v })"
            @update:round="(v: number | null) => setQuery({ round: v === null ? null : String(v) })"
            @update:query="(v: string) => setQuery({ q: v })"
            @reset="resetFilters"
          />
        </aside>

        <section class="feed__main" :aria-label="t('views.run.simFeed.ariaLabel')">
          <p v-if="loadingInitial" class="feed__state" role="status" data-testid="feed-loading">
            {{ t('views.run.simFeed.states.loading') }}
          </p>
          <p
            v-else-if="entryCount === 0 && !feed.error.value"
            class="feed__state"
            role="status"
            data-testid="feed-empty"
          >
            {{ filtersActive ? t('views.run.simFeed.states.emptyFiltered') : t('views.run.simFeed.states.empty') }}
          </p>
          <ul
            v-if="entryCount > 0"
            class="feed__list"
            :aria-label="t(`views.run.simFeed.timeline.${network}`)"
            data-testid="feed-list"
          >
            <li v-for="entry in twitterEntries" :key="entry.post.post_id">
              <TwitterCard
                :entry="entry"
                :to="postTo(entry.post.post_id)"
                :selected="selectedPersonaId === entry.post.persona_id"
                @open="openPost(entry.post.post_id)"
                @focus="(id: string) => (focusedPersonaId = id)"
              />
            </li>
            <li v-for="entry in redditEntries" :key="entry.post.post_id">
              <RedditRow
                :entry="entry"
                :to="postTo(entry.post.post_id)"
                :selected="selectedPersonaId === entry.post.persona_id"
                @open="openPost(entry.post.post_id)"
                @focus="(id: string) => (focusedPersonaId = id)"
              />
            </li>
          </ul>
        </section>

        <aside id="feed-right" class="feed__aside" :class="{ 'feed__aside--collapsed': !rightOpen }">
          <PersonaCard :persona="selectedPersona" :fallback-name="fallbackName" :interview-to="interviewTo" />
          <RoundPanel
            :round="panelRound"
            :total="runState.totalRounds.value"
            :twitter="activity.twitter"
            :reddit="activity.reddit"
          />
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.feed {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.feed__toggles {
  display: none;
  gap: 8px;
}
.feed__toggle {
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.feed__toggle:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.feed__grid {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 280px;
  gap: 16px;
  align-items: start;
}
.feed__aside {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.feed__main {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.feed__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.feed__state {
  margin: 0;
  padding: 16px;
  border: 1px dashed var(--line);
  border-radius: var(--ag-r-12);
  color: var(--fg2);
  font-size: 13px;
}
@media (max-width: 1023px) {
  .feed__toggles {
    display: flex;
  }
  .feed__grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .feed__aside--collapsed {
    display: none;
  }
}
</style>
