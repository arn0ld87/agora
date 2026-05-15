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
 * Mappt einen Sentiment-Wert auf einen CSS-Klassen-Namen.
 * null → 'neutral-dim' (Sentiment-Service inaktiv)
 * [-1, -0.33) → 'negative'
 * [-0.33, 0.33] → 'neutral'
 * (0.33, 1] → 'positive'
 */
function sentimentClass(s: number | null | undefined): string {
  if (s == null) return 'sentiment-null'
  if (s < -0.33) return 'sentiment-negative'
  if (s > 0.33) return 'sentiment-positive'
  return 'sentiment-neutral'
}

const heatbarPulses = computed(() => {
  const posts = props.recentPosts ?? []
  if (posts.length === 0) return []
  return posts.map((p) => sentimentClass(p.sentiment))
})

/** true wenn alle sentiments null/undefined → "Sentiment-Service nicht aktiv" Hinweis */
const allSentimentNull = computed(() => {
  const posts = props.recentPosts ?? []
  return posts.length > 0 && posts.every((p) => p.sentiment == null)
})
</script>

<template>
  <div class="spb-root" role="status" :aria-label="t('feed.live')">
    <div class="spb-bar" :aria-label="t('feed.sentimentBar')" role="img">
      <!-- Sentiment-Heatbar: ein Segment pro Post aus recentPosts -->
      <template v-if="heatbarPulses.length > 0">
        <div
          v-for="(cls, idx) in heatbarPulses"
          :key="idx"
          class="spb-pulse"
          :class="[cls, { 'spb-pulse--dim': allSentimentNull }]"
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
  background: var(--surface-subtle, #f9fafb);
  border-bottom: 1px solid var(--hairline, #e5e7eb);
}
.spb-bar {
  height: 4px;
  border-radius: 2px;
  overflow: hidden;
  background: var(--surface-muted, #e5e7eb);
  display: flex;
  gap: 1px;
}
/* Fallback: einfarbige Füllung wenn keine Posts vorhanden */
.spb-fill {
  height: 100%;
  width: 100%;
  background: var(--accent, #2563eb);
  opacity: 0.6;
  border-radius: 2px;
}
/* Sentiment-Pulse-Segmente */
.spb-pulse {
  flex: 1;
  height: 100%;
  border-radius: 1px;
  transition: background-color 0.3s ease;
}
.spb-pulse.sentiment-negative {
  background: var(--status-red, #dc2626);
}
.spb-pulse.sentiment-neutral {
  background: var(--text-tertiary, #6b7280);
}
.spb-pulse.sentiment-positive {
  background: var(--status-green, #10b981);
}
.spb-pulse.sentiment-null {
  background: var(--text-tertiary, #6b7280);
  opacity: 0.4;
}
/* Alle null → Pulse-Animation als visueller Hinweis */
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
  color: var(--text-secondary, #6b7280);
  flex-wrap: wrap;
}
.spb-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--status-green, #10b981);
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
  color: var(--status-green, #10b981);
}
.spb-divider {
  color: var(--hairline, #d1d5db);
}
.spb-rate,
.spb-count,
.spb-reddit,
.spb-twitter {
  color: var(--text-secondary, #6b7280);
}
</style>
