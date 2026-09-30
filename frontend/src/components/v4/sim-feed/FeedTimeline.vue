<script setup lang="ts">
/**
 * FeedTimeline — virtualisierte, chronologische Beitragsliste.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.5, §4. Ersetzt die
 * Dual-Column-Struktur (`.sf-columns`) in StepSimulationFeedView.vue.
 *
 * Kein Scroll-Sprung: solange der Nutzer den unteren Sichtbereich verlassen
 * hat (> 120px vom Ende), bleibt die Liste stehen und `NewItemsPill` zeigt
 * den Zaehler neu angekommener Beitraege. Am unteren Rand haengt sie ohne
 * Sprung an. Virtualisierung ueber @tanstack/vue-virtual, estimateSize=120,
 * overscan=6.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { useI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import FeedItem from './FeedItem.vue'
import NewItemsPill from './NewItemsPill.vue'

export interface FeedTimelineError {
  code: string
  message: string
}

const props = defineProps<{
  items: PostCreatedEvent[]
  // 'connecting' ist ein eigener Zustand (Erstverbindung) und zeigt KEINEN
  // Reconnect-Banner — nur 'reconnecting' (Verbindung war offen und ist
  // abgebrochen) tut das. Vorher wurde 'connecting' vom Aufrufer auf
  // 'reconnecting' gemappt, was beim ersten Laden faelschlich den
  // "Verbindung verloren"-Banner zeigte.
  streamState: 'connecting' | 'open' | 'reconnecting' | 'closed' | 'ended'
  isSnapshotLoading: boolean
  error: FeedTimelineError | null
}>()

const emit = defineEmits<{ openThread: [postId: string]; retry: [] }>()

const { t } = useI18n()

const scrollEl = ref<HTMLElement | null>(null)
const isAtBottom = ref(true)
const pillCount = ref(0)
const newIds = ref<Set<string>>(new Set())

let prevIds = new Set<string>()
let baselineCaptured = false

const virtualizer = useVirtualizer(
  computed(() => ({
    count: props.items.length,
    getScrollElement: () => scrollEl.value,
    estimateSize: () => 120,
    overscan: 6,
  })),
)

const virtualRows = computed(() => virtualizer.value.getVirtualItems())
const totalSize = computed(() => virtualizer.value.getTotalSize())

function onScroll(): void {
  const el = scrollEl.value
  if (!el) return
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  isAtBottom.value = distanceFromBottom < 120
  if (isAtBottom.value) pillCount.value = 0
}

function scrollToBottom(): void {
  pillCount.value = 0
  nextTick(() => {
    virtualizer.value.scrollToIndex(props.items.length - 1, { align: 'end' })
  })
}

watch(
  () => props.items,
  (list) => {
    if (!baselineCaptured) {
      prevIds = new Set(list.map((p) => p.post_id))
      baselineCaptured = true
      return
    }
    const added: PostCreatedEvent[] = list.filter((p) => !prevIds.has(p.post_id))
    prevIds = new Set(list.map((p) => p.post_id))
    if (added.length === 0) return
    for (const p of added) newIds.value.add(p.post_id)
    if (isAtBottom.value) {
      nextTick(() => virtualizer.value.scrollToIndex(list.length - 1, { align: 'end' }))
    } else {
      pillCount.value += added.length
    }
  },
  { flush: 'post' },
)
</script>

<template>
  <div class="ft-root">
    <div
      v-if="streamState === 'reconnecting'"
      class="ft-banner ft-banner--warn"
      role="status"
    >
      {{ t('feed.streamLost', { attempt: 1 }) }}
    </div>

    <div v-if="error" class="ft-banner ft-banner--error" role="alert">
      <span>{{ error.message }}</span>
      <button type="button" class="ft-retry" @click="emit('retry')">
        {{ t('feed.rounds.retry') }}
      </button>
    </div>

    <div v-if="isSnapshotLoading" class="ft-skeleton" aria-busy="true">
      <div v-for="i in 3" :key="i" class="ft-skeleton-row"></div>
    </div>

    <p v-else-if="items.length === 0" class="ft-empty" role="status">
      {{ t('feed.noPosts') }}
      <span class="ft-empty-hint">{{ t('feed.noPostsHint') }}</span>
    </p>

    <div
      v-else
      ref="scrollEl"
      class="ft-scroll"
      :role="items.length > 0 ? 'feed' : 'region'"
      :aria-label="t('feed.feedTab')"
      @scroll="onScroll"
    >
      <div class="ft-spacer" :style="{ height: `${totalSize}px`, position: 'relative' }">
        <div
          v-for="row in virtualRows"
          :key="items[row.index].post_id"
          class="ft-row"
          :style="{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            transform: `translateY(${row.start}px)`,
          }"
        >
          <FeedItem
            :post="items[row.index]"
            :is-new="newIds.has(items[row.index].post_id)"
            @open-thread="(postId) => emit('openThread', postId)"
          />
        </div>
      </div>
    </div>

    <!--
      DOM-Position bewusst NACH der Timeline (§6 Punkt 9: Tab-Reihenfolge
      Filter -> Timeline -> Pill). Die visuelle Position "oberhalb der
      Liste" (§2.6) kommt ausschliesslich aus `order: -1` in
      NewItemsPill.vue, nicht aus der Dokumentreihenfolge.
    -->
    <NewItemsPill :count="pillCount" :visible="pillCount > 0" @click="scrollToBottom" />
  </div>
</template>

<style scoped>
.ft-root {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.ft-scroll {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.ft-banner {
  padding: 8px var(--sim-header-px);
  font-size: var(--sim-time-fs);
  text-align: center;
}
.ft-banner--warn {
  background: var(--status-warning-soft, var(--status-orange-bg));
  color: var(--status-warning, var(--status-orange));
}
.ft-banner--error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--status-red-bg);
  color: var(--status-red);
}
.ft-retry {
  border: 1px solid currentColor;
  border-radius: var(--r-5);
  background: transparent;
  color: inherit;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
}
.ft-skeleton {
  padding: var(--sim-item-py) var(--sim-item-px);
  display: flex;
  flex-direction: column;
  gap: var(--sim-item-gap);
}
.ft-skeleton-row {
  height: 64px;
  border-radius: var(--r-5);
  background: var(--surface-inset);
  animation: ft-shimmer 1.4s ease-in-out infinite;
}
@keyframes ft-shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
@media (prefers-reduced-motion: reduce) {
  .ft-skeleton-row {
    animation: none;
  }
}
.ft-empty {
  margin: 0;
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ft-empty-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
