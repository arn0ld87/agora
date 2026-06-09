<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Kicker from '@/components/v4/data/Kicker.vue'

const { t } = useI18n()

defineProps({
  totalActions: { type: Number, required: true },
  twitterActions: { type: Number, required: true },
  redditActions: { type: Number, required: true },
  currentSimTime: { type: [Date, null], default: null },
  simElapsedSec: { type: Number, default: 0 },
})

const _berlinFormatter = new Intl.DateTimeFormat('de-DE', {
  dateStyle: 'short',
  timeStyle: 'medium',
  timeZone: 'Europe/Berlin',
})

function formatBerlin(d: Date | null): string {
  return d ? _berlinFormatter.format(d) : ''
}

function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`
}
</script>

<template>
  <article class="card" data-testid="simulation-progress-panel">
    <header class="card-head">
      <Kicker num="02">{{ t('step3.feed.title') }}</Kicker>
      <span class="meta">{{ t('step3.feed.actions', { count: totalActions }) }}</span>
      <div v-if="currentSimTime" class="sim-clock" :title="t('step3.simClock.tooltip')">
        <span class="meta">SIM</span>
        <time :datetime="currentSimTime.toISOString()">{{ formatBerlin(currentSimTime) }}</time>
        <span class="meta">({{ formatElapsed(simElapsedSec) }})</span>
      </div>
    </header>
    <div class="stats-grid">
      <div class="stat">
        <span class="stat-value">{{ totalActions }}</span>
        <span class="stat-label">{{ t('step3.feed.actions', { count: '' }).replace(':', '').trim() }}</span>
      </div>
      <div class="stat">
        <span class="stat-value">{{ twitterActions }}</span>
        <span class="stat-label">Twitter</span>
      </div>
      <div class="stat">
        <span class="stat-value">{{ redditActions }}</span>
        <span class="stat-label">Reddit</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.card {
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card-head {
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--rule);
}
.stat {
  padding: var(--s-3) var(--s-3) var(--s-3) 0;
  border-right: 1px solid var(--rule);
}
.stat:last-child { border-right: 0; }
.stat-value {
  display: block;
  font-family: var(--ff-sans);
  font-weight: 600;
  font-size: var(--fs-32);
  color: var(--fg);
  line-height: 1;
  letter-spacing: -0.02em;
}
.stat-label {
  display: block;
  margin-top: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.sim-clock {
  display: inline-flex;
  align-items: baseline;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  color: var(--fg);
}
.sim-clock time { color: var(--accent); }
.meta { color: var(--fg-muted); font-family: var(--ff-mono); font-size: 11px; letter-spacing: var(--ls-mono); }
</style>
