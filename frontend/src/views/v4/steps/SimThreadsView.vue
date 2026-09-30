<script setup lang="ts">
/**
 * SimThreadsView — Diskurs-Übersicht (Kind-Route `threads` von
 * SimulationLayout.vue). Slice UI-2b (#1713), Commit 2: Platzhalter mit
 * konsistentem Empty-State; die eigentliche `SimThreadList` folgt in
 * Commit 4 (docs/design/simulation-feed.md §2.7).
 */
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="sim-threads-root">
    <p class="sim-threads-empty" role="status">{{ t('feed.threadsPlaceholder') }}</p>
  </div>
</template>

<style scoped>
.sim-threads-root {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.sim-threads-empty {
  margin: 0;
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
