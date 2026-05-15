<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  activityRate: number
  redditCount: number
  twitterCount: number
}>()

const { t } = useI18n()

const rateDisplay = computed(() => {
  const r = props.activityRate
  if (r < 0.1) return '< 0.1'
  return r.toFixed(1)
})

const totalCount = computed(() => props.redditCount + props.twitterCount)
</script>

<template>
  <div class="spb-root" role="status" :aria-label="t('feed.live')">
    <div class="spb-bar">
      <!-- Einfarbige Heatbar (Accent) — Sentiment-Feld folgt in Followup-Slice -->
      <div class="spb-fill"></div>
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
}
.spb-fill {
  height: 100%;
  width: 100%;
  background: var(--accent, #2563eb);
  opacity: 0.6;
  border-radius: 2px;
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
