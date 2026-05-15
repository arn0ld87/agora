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
  border-radius: 3px;
  background: var(--status-amber-bg, rgba(255, 200, 50, 0.18));
  color: var(--status-amber, #b45309);
  text-transform: uppercase;
  flex-shrink: 0;
}
</style>
