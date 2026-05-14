<script setup lang="ts">
/**
 * RunDetailAppShellView — AppShell-Wrapper fuer RunDetailView (Slice F, Design-v4).
 *
 * RunDetailView.vue bleibt unveraendert — kein inhaltlicher Refactor.
 * Breadcrumbs: ["Runs", "<runId>"].
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import RunDetailView from '../RunDetailView.vue'

const route = useRoute()
const runId = computed(() => String(route.params['id'] ?? ''))

const breadcrumbs = computed(() => [
  { label: 'Runs', to: { name: 'Runs' } },
  { label: runId.value || 'Detail' },
])
</script>

<template>
  <AppShell :breadcrumbs="breadcrumbs">
    <RunDetailView />
  </AppShell>
</template>
