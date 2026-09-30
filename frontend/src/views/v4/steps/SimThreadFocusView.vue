<script setup lang="ts">
/**
 * SimThreadFocusView — Strang-Fokus (Kind-Route `thread/:postId` von
 * SimulationLayout.vue). Slice UI-2b (#1713), Commit 2: Platzhalter mit
 * konsistentem Empty-State; die eigentliche `SimThreadTree` folgt in
 * Commit 4 (docs/design/simulation-feed.md §2.8).
 */
import { useI18n } from 'vue-i18n'

defineProps<{ postId: string }>()

const { t } = useI18n()
</script>

<template>
  <div class="sim-thread-focus-root">
    <p class="sim-thread-focus-empty" role="status">{{ t('feed.threadFocusPlaceholder') }}</p>
  </div>
</template>

<style scoped>
.sim-thread-focus-root {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}
.sim-thread-focus-empty {
  margin: 0;
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
