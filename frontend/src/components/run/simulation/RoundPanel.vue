<script setup lang="ts">
/**
 * „Runde x von y" mit Aktivität je Netzwerk (#1801), rechte Spalte unter der
 * Persona-Karte.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  round: number | null
  total: number | null
  twitter: number
  reddit: number
}>()
const { t } = useI18n()

const title = computed(() => {
  if (props.round === null) return t('views.run.simFeed.roundPanel.titleNone')
  if (!props.total) return t('views.run.simFeed.roundPanel.titleUnknownTotal', { round: props.round })
  return t('views.run.simFeed.roundPanel.title', { round: props.round, total: props.total })
})
</script>

<template>
  <section class="rp" :aria-label="title" data-testid="round-panel">
    <h3 class="rp__title" data-testid="round-panel-title">{{ title }}</h3>
    <template v-if="round !== null">
      <p class="rp__label">{{ t('views.run.simFeed.roundPanel.activity') }}</p>
      <p v-if="twitter + reddit > 0" class="rp__line" data-testid="round-panel-activity">
        {{ t('views.run.simFeed.roundPanel.activityLine', { twitter, reddit }) }}
      </p>
      <p v-else class="rp__line rp__line--muted" data-testid="round-panel-activity">
        {{ t('views.run.simFeed.roundPanel.activityNone') }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.rp {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}
.rp__title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 650;
}
.rp__label {
  margin: 0;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.rp__line {
  margin: 2px 0 0;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.rp__line--muted {
  color: var(--fg2);
}
</style>
