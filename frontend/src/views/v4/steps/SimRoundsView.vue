<script setup lang="ts">
/**
 * SimRoundsView — Runden-Ansicht (Kind-Route `rounds` von
 * SimulationLayout.vue). Slice UI-2b (#1713), Commit 2: Platzhalter mit
 * konsistentem Empty-State; die eigentliche `SimRoundsList` folgt in
 * Commit 4 (docs/design/simulation-feed.md §2.9).
 */
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="sim-rounds-root">
    <p class="sim-rounds-empty" role="status">{{ t('feed.roundsPlaceholder') }}</p>
  </div>
</template>

<style scoped>
.sim-rounds-root {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.sim-rounds-empty {
  margin: 0;
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
