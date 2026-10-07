<script setup lang="ts">
/**
 * Hinweise zum Feed (#1801): Ladefehler, abgeschnittener Snapshot, verworfene
 * und verdrängte Beiträge, Beiträge ohne Rundenangabe, unterbrochener Strom.
 * Nichts davon bleibt still.
 */
import { useI18n } from 'vue-i18n'

defineProps<{
  error: string | null
  truncated: boolean
  limit: number
  invalidCount: number
  evictedCount: number
  /** Beiträge ohne Rundenangabe; nur im Rückblick relevant, sonst 0 übergeben. */
  unroundedCount: number
  streamError: boolean
}>()
const emit = defineEmits<{ reload: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="notices" data-testid="feed-notices">
    <p v-if="error" class="notices__item notices__item--err" role="alert" data-testid="notice-error">
      <span>{{ t('views.run.simFeed.notices.error', { message: error }) }}</span>
      <button type="button" class="notices__retry" data-testid="notice-retry" @click="emit('reload')">
        {{ t('views.run.simFeed.notices.retry') }}
      </button>
    </p>
    <p v-if="streamError" class="notices__item" role="status" data-testid="notice-stream">
      {{ t('views.run.simFeed.notices.stream') }}
    </p>
    <p v-if="truncated" class="notices__item" role="status" data-testid="notice-truncated">
      {{ t('views.run.simFeed.notices.truncated', { limit }) }}
    </p>
    <p v-if="invalidCount > 0" class="notices__item" role="status" data-testid="notice-invalid">
      {{ t('views.run.simFeed.notices.invalid', { count: invalidCount }) }}
    </p>
    <p v-if="evictedCount > 0" class="notices__item" role="status" data-testid="notice-evicted">
      {{ t('views.run.simFeed.notices.evicted', { count: evictedCount }) }}
    </p>
    <p v-if="unroundedCount > 0" class="notices__item" role="status" data-testid="notice-unrounded">
      {{ t('views.run.simFeed.notices.unrounded', { count: unroundedCount }) }}
    </p>
  </div>
</template>

<style scoped>
.notices {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.notices__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 6px 10px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 13px;
}
.notices__item--err {
  background: var(--err-soft);
  color: var(--err);
}
.notices__retry {
  padding: 2px 10px;
  border: 1px solid currentColor;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.notices__retry:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
</style>
