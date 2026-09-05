<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const props = defineProps<{
  activityRate: number
  redditCount: number
  twitterCount: number
  recentPosts?: PostCreatedEvent[]
}>()

const { t } = useI18n()

const rateDisplay = computed(() => {
  const r = props.activityRate
  if (r < 0.1) return '< 0.1'
  return r.toFixed(1)
})

const totalCount = computed(() => props.redditCount + props.twitterCount)

/**
 * Mappt den Voting-Score eines Posts auf einen CSS-Klassen-Namen.
 *
 * #1209 5b: Die Leiste zeigte zuvor `sentiment` — ein Feld, das nie einen Wert
 * trug, also garantiert immer im „nicht erhoben“-Zweig landete und trotzdem wie
 * eine Messung aussah. Sie zeigt jetzt `score` (num_likes - num_dislikes aus der
 * Simulations-DB), einen tatsächlich erhobenen Wert. 0 heißt „keine Votes“, nicht
 * „nicht gemessen“.
 *
 * score < 0 → negative (Widerspruch), 0 → neutral, > 0 → positive (Zustimmung)
 */
function scoreClass(s: number | null | undefined): string {
  const value = s ?? 0
  if (value < 0) return 'score-negative'
  if (value > 0) return 'score-positive'
  return 'score-neutral'
}

const heatbarPulses = computed(() => {
  const posts = props.recentPosts ?? []
  if (posts.length === 0) return []
  return posts.map((p) => scoreClass(p.score))
})

/** true wenn kein Post Resonanz erfahren hat — die Leiste wird gedimmt, damit
 * „alle neutral“ nicht wie ein ausgewogenes Meinungsbild aussieht. */
const noResonanceYet = computed(() => {
  const posts = props.recentPosts ?? []
  return posts.length > 0 && posts.every((p) => (p.score ?? 0) === 0)
})
</script>

<template>
  <div class="spb-root" role="status" :aria-label="t('feed.live')">
    <div class="spb-bar" :aria-label="t('feed.resonanceBar')" role="img">
      <!-- Resonanz-Leiste: ein Segment pro Post aus recentPosts, eingefärbt
           nach Voting-Score (#1209 5b). -->
      <template v-if="heatbarPulses.length > 0">
        <div
          v-for="(cls, idx) in heatbarPulses"
          :key="idx"
          class="spb-pulse"
          :class="[cls, { 'spb-pulse--dim': noResonanceYet }]"
        ></div>
      </template>
      <!-- Fallback wenn keine Posts vorhanden -->
      <div v-else class="spb-fill"></div>
    </div>
    <div class="spb-stats">
      <span class="spb-live-dot" aria-hidden="true"></span>
      <span class="spb-label">{{ t('feed.live') }}</span>
      <span class="spb-divider" aria-hidden="true">·</span>
      <span class="spb-rate">{{ rateDisplay }} {{ t('feed.activity') }}</span>
      <span class="spb-divider" aria-hidden="true">·</span>
      <span class="spb-count">{{ totalCount }} Posts</span>
      <span class="spb-divider" aria-hidden="true">·</span>
      <span class="spb-reddit">Reddit: {{ redditCount }}</span>
      <span class="spb-divider" aria-hidden="true">·</span>
      <span class="spb-twitter">Twitter: {{ twitterCount }}</span>
    </div>
  </div>
</template>

<style scoped>
.spb-root {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px;
  background: var(--surface-inset);
  border-bottom: 1px solid var(--hairline);
}
.spb-bar {
  height: 4px;
  border-radius: 2px;
  overflow: hidden;
  background: var(--gray-5);
  display: flex;
  gap: 1px;
}
/* Fallback: einfarbige Füllung wenn keine Posts vorhanden */
.spb-fill {
  height: 100%;
  width: 100%;
  background: var(--accent);
  opacity: 0.6;
  border-radius: 2px;
}
/* Resonanz-Segmente, eingefärbt nach Voting-Score */
.spb-pulse {
  flex: 1;
  height: 100%;
  border-radius: 1px;
  transition: background-color 0.3s ease;
}
.spb-pulse.score-negative {
  background: var(--status-red);
}
.spb-pulse.score-neutral {
  background: var(--text-tertiary);
}
.spb-pulse.score-positive {
  background: var(--status-green);
}
/* Noch keine Resonanz → Pulse-Animation als visueller Hinweis */
.spb-pulse--dim {
  animation: pulse-dim 1.8s ease-in-out infinite;
}
@keyframes pulse-dim {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.15; }
}
@media (prefers-reduced-motion: reduce) {
  .spb-pulse--dim {
    animation: none;
  }
}
.spb-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.spb-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--status-green);
  animation: pulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
@media (prefers-reduced-motion: reduce) {
  .spb-live-dot {
    animation: none;
  }
}
.spb-label {
  font-weight: 600;
  color: var(--status-green);
}
.spb-divider {
  color: var(--hairline);
}
.spb-rate,
.spb-count,
.spb-reddit,
.spb-twitter {
  color: var(--text-secondary);
}
</style>
