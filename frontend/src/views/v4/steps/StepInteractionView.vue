<!--
  StepInteractionView — AppShell-Wrapper fuer Step 5 (Interaktion).
  Der Inhalt (Step5Interaction.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      :title="$t('views.stepInteraction.title')"
      :subtitle="$t('views.stepInteraction.subtitle')"
    />
    <PipelineStepper :current-step="5" />
    <Step5Interaction
      :report-id="reportId"
      :simulation-id="runIdFromQuery ?? undefined"
    />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step5Interaction from '@/components/Step5Interaction.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  reportId: string
}>()

// Die Route /v4/interaction/:reportId kennt nur die reportId. Chat, Interview
// und Profil-Liste brauchen aber die simulation_id. Analog zu StepReportView
// wird ?runId=... durchgereicht; fehlt der Query-Param, faellt
// Step5Interaction auf die simulation_id aus dem geladenen Report zurueck.
const route = useRoute()
const runIdFromQuery = computed<string | null>(() => {
  const value = route.query.runId
  return typeof value === 'string' && value.length > 0 ? value : null
})

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.reportId },
  { label: 'Interaktion' },
])
</script>
