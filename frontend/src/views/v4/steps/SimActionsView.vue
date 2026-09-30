<script setup lang="ts">
/**
 * SimActionsView — Protokoll-Ansicht (Kind-Route `actions` von
 * SimulationLayout.vue). Slice UI-2b (#1713), Commit 2: Platzhalter mit
 * konsistentem Empty-State; die eigentliche `SimActionsTable` folgt in
 * Commit 6 (docs/design/simulation-feed.md §2.10).
 */
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="sim-actions-root">
    <p class="sim-actions-empty" role="status">{{ t('feed.actionsPlaceholder') }}</p>
  </div>
</template>

<style scoped>
.sim-actions-root {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.sim-actions-empty {
  margin: 0;
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
