<!--
  HistoryView — v4-Shell-Wrapper fuer HistoryDatabase.
  Slice I: AppShell + PageHeader; HistoryDatabase bleibt unveraendert.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader :title="$t('views.history.title')" :subtitle="$t('views.history.subtitle')" />
    <HistoryDatabase />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import HistoryDatabase from '@/components/HistoryDatabase.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const { t } = useI18n()
const crumbs = computed<BreadcrumbItem[]>(() => [{ label: t('views.history.title') }])
</script>
