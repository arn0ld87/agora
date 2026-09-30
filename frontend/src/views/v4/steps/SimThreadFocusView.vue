<script setup lang="ts">
/**
 * SimThreadFocusView — Strang-Fokus (Kind-Route `thread/:postId` von
 * SimulationLayout.vue). Slice UI-2b (#1713), Commit 4
 * (docs/design/simulation-feed.md §2.8).
 *
 * `Esc` geht route-basiert zurueck zu `SimThreads` (nicht `history.back()` —
 * §6 Punkt 9: ein History-Hack koennte aus einem Deep-Link in eine leere
 * Historie zurueckspringen).
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useEventStream } from '@/composables/useEventStream'
import { useSimFeed, collectThreadNodes } from '@/composables/useSimFeed'
import { getSimulationFeedSnapshot } from '@/api/simulation'
import SimThreadTree from '@/components/v4/sim-feed/SimThreadTree.vue'
import SimRunHeader, { type StreamState } from '@/components/v4/sim-feed/SimRunHeader.vue'

const props = defineProps<{ postId: string }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const simulationId = String(route.params.simulationId)
const feed = useSimFeed(simulationId)

const stream = useEventStream(simulationId, {
  post_created: (data) => feed.ingest(data),
})

const isSnapshotLoading = ref(true)
const streamStarted = ref(false)

async function loadSnapshot(): Promise<void> {
  isSnapshotLoading.value = true
  const [reddit, twitter] = await Promise.all([
    getSimulationFeedSnapshot(simulationId, 'reddit').catch(() => null),
    getSimulationFeedSnapshot(simulationId, 'twitter').catch(() => null),
  ])
  feed.ingestMany([...(reddit ?? []), ...(twitter ?? [])])
  isSnapshotLoading.value = false
}

onMounted(async () => {
  await stream.start()
  streamStarted.value = true
  // Bereits geladene Simulationen (z.B. Wechsel von der Feed-Ansicht) haben
  // den Snapshot schon im Store — ein erneuter Ladevorgang waere sichtbares
  // Flackern ohne Nutzen.
  if (feed.flatTimeline.value.length === 0) {
    await loadSnapshot()
  } else {
    isSnapshotLoading.value = false
  }
})

onBeforeUnmount(() => {
  feed.flushPending()
  stream.stop()
})

const root = computed(() => feed.byId(props.postId))

const nodes = computed(() => (root.value ? collectThreadNodes(root.value.post_id, feed.flatTimeline.value) : []))

const streamState = computed<StreamState>(() => {
  if (!streamStarted.value) return 'connecting'
  if (stream.error.value) return 'reconnecting'
  if (stream.isStreaming.value) return 'open'
  return 'closed'
})

const currentRound = computed<number | null>(() => root.value?.round_num ?? null)
const lastSimTime = computed<string | null>(() => root.value?.sim_time ?? root.value?.timestamp ?? null)

function goBack(): void {
  void router.push({ name: 'SimThreads', query: route.query })
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    goBack()
  }
}

function openThread(postId: string): void {
  void router.push({ name: 'SimThreadFocus', params: { simulationId, postId }, query: route.query })
}
</script>

<template>
  <div class="stf-root" tabindex="-1" @keydown="onKeydown">
    <SimRunHeader
      :simulation-id="simulationId"
      :current-round="currentRound"
      :total-rounds="null"
      :sim-time="lastSimTime"
      :post-count="nodes.length + (root ? 1 : 0)"
      :stream-state="streamState"
      :degradation="null"
      :loading="isSnapshotLoading && !root"
    />
    <SimThreadTree
      v-if="root"
      :root="root"
      :nodes="nodes"
      :loading="false"
      @open-thread="openThread"
    />
    <p v-else-if="!isSnapshotLoading" class="stf-empty" role="status">
      {{ t('feed.threadFocusPlaceholder') }}
    </p>
    <div v-else class="stf-loading" aria-busy="true">
      <p class="stf-loading-text" role="status">{{ t('feed.threadTree.loading') }}</p>
    </div>
  </div>
</template>

<style scoped>
.stf-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  outline: none;
}
.stf-empty,
.stf-loading-text {
  margin: 0;
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
