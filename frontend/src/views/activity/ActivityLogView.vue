<script setup lang="ts">
/**
 * Aktivität → Protokoll (Etappe 2, Ticket 5, #1797): dieselbe Protokoll-
 * Komponente wie die Konsole, als ganze Seite. Solange die Seite offen ist,
 * hält sie den Strom allein (die Konsole ist dann ausgeblendet), es gibt nie
 * zwei Verbindungen zu `/api/logs/stream`.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import ActivityTabs from '@/components/activity/ActivityTabs.vue'
import LogStream from '@/components/activity/LogStream.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useLogStreamPageClaim } from '@/composables/useLogDrawer'

const { t } = useI18n()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.activity.title'), path: '/activity/jobs' },
  { label: t('views.activity.log.title') },
])
useShellBreadcrumbs(crumbs)
useLogStreamPageClaim()
</script>

<template>
  <section class="activity-log">
    <PageHeader :title="t('views.activity.title')" />
    <ActivityTabs />
    <div class="log-card">
      <LogStream :title="t('views.activity.log.pageTitle')" />
    </div>
  </section>
</template>

<style scoped>
.activity-log { display: flex; flex-direction: column; min-height: 0; }
.log-card {
  display: flex; flex-direction: column;
  height: calc(100vh - 260px); min-height: 320px;
  background: var(--s2); border-radius: var(--ag-r-12); overflow: hidden;
}
</style>
