<script setup lang="ts">
/**
 * StatsRow — vier Mikro-Kennzahlen für das Dashboard.
 * Workbench-These: dichte Information, ruhig, mono-Zahlen, dünne Hairlines.
 */
defineProps<{
  activeRuns: number
  completedToday: number
  avgConfidence: number | null
  personas: number
}>()
</script>

<template>
  <div class="stats-row" role="list">
    <div class="stats-cell" role="listitem">
      <div class="stats-cell__value">{{ activeRuns }}</div>
      <div class="stats-cell__label">{{ $t('dashboard.stats.activeRuns') }}</div>
    </div>
    <div class="stats-cell" role="listitem">
      <div class="stats-cell__value">{{ completedToday }}</div>
      <div class="stats-cell__label">{{ $t('dashboard.stats.completedToday') }}</div>
    </div>
    <div class="stats-cell" role="listitem">
      <div class="stats-cell__value">
        <template v-if="avgConfidence === null"><span class="stats-cell__dim">—</span></template>
        <template v-else>{{ Math.round(avgConfidence * 100) }}<span class="stats-cell__unit">%</span></template>
      </div>
      <div class="stats-cell__label">{{ $t('dashboard.stats.avgConfidence') }}</div>
    </div>
    <div class="stats-cell" role="listitem">
      <div class="stats-cell__value">{{ personas }}</div>
      <div class="stats-cell__label">{{ $t('dashboard.stats.personas') }}</div>
    </div>
  </div>
</template>

<style scoped>
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--hairline);
  border-radius: var(--r-6, 12px);
  overflow: hidden;
  box-shadow: 0 0 0 1px var(--hairline);
}

.stats-cell {
  background: var(--surface-elevated);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stats-cell__value {
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  line-height: 1.1;
  white-space: nowrap;
}

.stats-cell__unit {
  font-size: 15px;
  color: var(--text-secondary);
  margin-left: 1px;
}

.stats-cell__dim {
  color: var(--text-quaternary);
}

.stats-cell__label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

@media (max-width: 720px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
