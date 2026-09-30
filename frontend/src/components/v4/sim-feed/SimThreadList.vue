<script setup lang="ts">
/**
 * SimThreadList — Diskurs-Uebersicht.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.7. Liste aller
 * Strang-Wurzeln, sortiert nach zuletzt aktivem Reply (die aufrufende View
 * liefert die Sortierung ueber `buildThreadSummaries()`). Trennlinien statt
 * Karten, kein Radius ausser dem Runden-Chip.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

export interface SimThreadListEntry {
  root: PostCreatedEvent
  replyCount: number
  repostCount: number
  quoteCount: number
  lastActivityAt: string
  activeRounds: number[]
}

const props = defineProps<{
  threads: SimThreadListEntry[]
  loading: boolean
  emptyReason: 'no_data' | 'filter' | null
}>()

const emit = defineEmits<{ open: [postId: string] }>()

const { t } = useI18n()

function roundLabel(rounds: number[]): string | null {
  if (rounds.length === 0) return null
  const min = rounds[0]
  const max = rounds[rounds.length - 1]
  return min === max ? `R${min}` : `R${min}–${max}`
}

function open(postId: string): void {
  emit('open', postId)
}

function onKeydown(event: KeyboardEvent, postId: string): void {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    open(postId)
  }
}

const emptyText = computed(() =>
  props.emptyReason === 'filter' ? t('feed.threadList.emptyFiltered') : t('feed.threadList.empty'),
)
</script>

<template>
  <div class="stl2-root">
    <div v-if="loading" class="stl2-skeleton" aria-busy="true">
      <div v-for="i in 5" :key="i" class="stl2-skeleton-row"></div>
    </div>

    <p v-else-if="threads.length === 0" class="stl2-empty" role="status">
      {{ emptyText }}
    </p>

    <ul v-else class="stl2-list" role="list">
      <li v-for="entry in threads" :key="entry.root.post_id" class="stl2-item">
        <div
          class="stl2-row"
          role="button"
          tabindex="0"
          @click="open(entry.root.post_id)"
          @keydown="(event) => onKeydown(event, entry.root.post_id)"
        >
          <span class="stl2-platform" :data-platform="entry.root.platform" aria-hidden="true">
            {{ entry.root.platform === 'reddit' ? 'R' : 'T' }}
          </span>
          <div class="stl2-content">
            <div class="stl2-head">
              <span class="stl2-persona">{{ entry.root.persona_name }}</span>
              <span v-if="roundLabel(entry.activeRounds)" class="stl2-round-chip">{{
                roundLabel(entry.activeRounds)
              }}</span>
            </div>
            <p class="stl2-excerpt">{{ entry.root.body }}</p>
            <div class="stl2-counts">
              <span>{{ t('feed.threadList.replies', { count: entry.replyCount }) }}</span>
              <span>{{ t('feed.threadList.reposts', { count: entry.repostCount }) }}</span>
              <span>{{ t('feed.threadList.quotes', { count: entry.quoteCount }) }}</span>
            </div>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.stl2-root {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.stl2-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.stl2-item + .stl2-item {
  border-top: var(--sim-item-divider);
}
.stl2-row {
  display: flex;
  gap: var(--sim-item-gap);
  padding: var(--sim-item-py) var(--sim-item-px);
  cursor: pointer;
}
.stl2-row:hover {
  background: var(--surface-hover);
}
.stl2-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.stl2-platform {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-top: 2px;
  border-radius: var(--r-2);
  background: var(--sim-badge-bg);
  color: var(--text-primary);
  font-size: 10px;
  font-weight: 700;
}
.stl2-content {
  flex: 1;
  min-width: 0;
}
.stl2-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}
.stl2-persona {
  font-weight: 600;
  font-size: var(--sim-persona-fs);
  color: var(--text-primary);
}
.stl2-round-chip {
  font-size: 11px;
  color: var(--text-tertiary);
}
.stl2-excerpt {
  margin: 0 0 4px;
  font-size: var(--sim-time-fs);
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-wrap: pretty;
}
.stl2-counts {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-tertiary);
}
.stl2-empty {
  margin: 0;
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
.stl2-skeleton {
  padding: var(--sim-item-py) var(--sim-item-px);
  display: flex;
  flex-direction: column;
  gap: var(--sim-item-gap);
}
.stl2-skeleton-row {
  height: 56px;
  border-radius: var(--r-5);
  background: var(--surface-inset);
  animation: stl2-shimmer 1.4s ease-in-out infinite;
}
@keyframes stl2-shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
@media (prefers-reduced-motion: reduce) {
  .stl2-skeleton-row {
    animation: none;
  }
}
</style>
