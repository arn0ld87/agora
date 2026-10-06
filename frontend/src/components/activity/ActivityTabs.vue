<script setup lang="ts">
/** Umschalter Jobs / Protokoll der Aktivität (zwei Adressen, ein Bereich). */
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <nav class="activity-tabs" :aria-label="t('views.activity.tabs')">
    <router-link class="tab" :to="{ name: 'ActivityJobs' }">{{ t('views.activity.jobs.title') }}</router-link>
    <router-link class="tab" :to="{ name: 'ActivityLog' }">{{ t('views.activity.log.title') }}</router-link>
  </nav>
</template>

<style scoped>
.activity-tabs { display: inline-flex; gap: 2px; padding: 2px; margin-bottom: 16px; border-radius: var(--ag-r-8); background: var(--s2); }
.tab {
  display: inline-flex; align-items: center; height: 28px; padding: 0 12px; border-radius: var(--ag-r-6);
  font-size: 12.5px; font-weight: 500; color: var(--fg2); text-decoration: none;
}
.tab:hover { color: var(--fg); }
.tab.router-link-exact-active, .tab[aria-current='page'] { background: var(--s4); color: var(--fg); font-weight: 600; }
.tab:focus-visible { outline: 2px solid var(--acc); outline-offset: 1px; }
</style>
