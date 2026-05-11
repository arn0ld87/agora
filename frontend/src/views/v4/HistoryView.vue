<!--
  HistoryView — v4-Shell-Wrapper fuer HistoryDatabase.
  Slice I: AppShell + PageHeader; HistoryDatabase bleibt unveraendert.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader title="Verlauf" subtitle="Run- und Branch-Historie" />
    <HistoryDatabase />
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import HistoryDatabase from '@/components/HistoryDatabase.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const crumbs: BreadcrumbItem[] = [{ label: 'Verlauf' }]
</script>
