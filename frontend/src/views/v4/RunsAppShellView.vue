<script setup lang="ts">
/**
 * RunsAppShellView — AppShell-Wrapper fuer RunsView (Slice F, Design-v4).
 *
 * RunsView.vue bleibt unveraendert (eigener Brand-Header bleibt voerst drin).
 * Slice H extrahiert RunsView-Inhalt in eigenstaendige Unterkomponenten.
 */
import AppShell from '@/components/v4/shell/AppShell.vue'
import RunsView from '../RunsView.vue'

const BREADCRUMBS = [{ label: 'Runs' }]
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <RunsView />
  </AppShell>
</template>
