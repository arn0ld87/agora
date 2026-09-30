<script setup lang="ts">
/**
 * SimThreadTree — Strang-Fokus, baumartig.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.8. Baut die
 * bestehende RedditThread.vue-Rekursion aus und wird fuer beide Plattformen
 * genutzt: Twitter-Antworten (kind='comment', nur parent_post_id) ergeben
 * eine flache Reply-Liste unter der Wurzel, weil ihre Elternkante direkt auf
 * die Wurzel zeigt; Reddit-Antworten mit parent_comment_id ergeben einen
 * echten Baum. Die Kanten werden einheitlich aus
 * `parent_comment_id ?? parent_post_id` gebaut (parentIdOf) — die einzige
 * Kante-Regel, sie funktioniert mit und ohne Slice-5-Backfill.
 *
 * Nicht virtualisiert (§4): Straenge sind typischerweise <50 Knoten und
 * Sprungziele ueber postId muessen sofort DOM-praesent sein.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import { parentIdOf } from '@/composables/useSimFeed'
import FeedItem from './FeedItem.vue'
import SimThreadTreeLevel from './SimThreadTreeLevel.vue'

const props = withDefaults(
  defineProps<{
    root: PostCreatedEvent
    nodes: PostCreatedEvent[]
    maxDepth?: number
    loading: boolean
  }>(),
  { maxDepth: 6 },
)

const emit = defineEmits<{ openThread: [postId: string] }>()

const { t } = useI18n()

// Orphan-Zustand (§2.8): die Wurzel selbst hat noch eine Elternkante, die
// der Snapshot nicht aufloesen konnte — sichtbarer Chip statt stillem
// Verschweigen der Luecke.
const isOrphan = computed(() => parentIdOf(props.root) !== null)

// Kinder je Elternteil (Wurzel oder ein Knoten aus `nodes`). Zeigt eine
// Elternkante auf einen im Snapshot fehlenden Post, landet der Knoten
// best-effort direkt unter der Wurzel statt verloren zu gehen.
const childrenMap = computed<Map<string, PostCreatedEvent[]>>(() => {
  const knownIds = new Set(props.nodes.map((n) => n.post_id))
  const map = new Map<string, PostCreatedEvent[]>()
  for (const node of props.nodes) {
    const parentId = parentIdOf(node)
    const bucket = parentId && knownIds.has(parentId) ? parentId : props.root.post_id
    if (!map.has(bucket)) map.set(bucket, [])
    map.get(bucket)!.push(node)
  }
  for (const bucket of map.values()) bucket.sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  return map
})

const rootChildren = computed(() => childrenMap.value.get(props.root.post_id) ?? [])

function openThread(postId: string): void {
  emit('openThread', postId)
}
</script>

<template>
  <div class="stt-root">
    <div v-if="loading" class="stt-skeleton" aria-busy="true">
      <FeedItem :post="root" :show-context="false" />
      <div v-for="i in 3" :key="i" class="stt-skeleton-row"></div>
    </div>
    <template v-else>
      <p v-if="isOrphan" class="stt-orphan-chip" role="status">
        {{ t('feed.threadTree.orphan') }}
      </p>
      <FeedItem :post="root" :show-context="false" @open-thread="openThread" />
      <SimThreadTreeLevel
        v-for="node in rootChildren"
        :key="node.post_id"
        :node="node"
        :children-map="childrenMap"
        :depth="1"
        :max-depth="maxDepth"
        @open-thread="openThread"
      />
    </template>
  </div>
</template>

<style scoped>
.stt-root {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.stt-orphan-chip {
  align-self: flex-start;
  margin: var(--sim-header-py) var(--sim-header-px) 0;
  padding: 2px 10px;
  border-radius: var(--r-2);
  background: var(--status-warning-soft, var(--status-orange-bg));
  color: var(--status-warning, var(--status-orange));
  font-size: var(--sim-time-fs);
  font-weight: 600;
}
.stt-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--sim-item-gap);
  padding-bottom: var(--sim-item-py);
}
.stt-skeleton-row {
  margin: 0 var(--sim-item-px);
  height: 56px;
  border-radius: var(--r-5);
  background: var(--surface-inset);
  animation: stt-shimmer 1.4s ease-in-out infinite;
}
@keyframes stt-shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
@media (prefers-reduced-motion: reduce) {
  .stt-skeleton-row {
    animation: none;
  }
}
</style>
