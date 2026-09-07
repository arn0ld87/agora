<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t, te } = useI18n()
const label = te('feed.simBadge') ? t('feed.simBadge') : 'SIM'
</script>

<template>
  <span class="sim-badge" :title="`${label} · simuliert (Wording-Glossar v1)`">{{ label }}</span>
</template>

<style scoped>
.sim-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.06em;
  border-radius: var(--r-2);
  background: var(--status-orange-bg);
  color: var(--status-orange);
  text-transform: uppercase;
  flex-shrink: 0;
}
</style>
