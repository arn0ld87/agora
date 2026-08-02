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
      :simulation-id="simulationIdFromQuery ?? undefined"
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
import { INTERACTION_SIMULATION_ID_QUERY_KEY } from '@/utils/reportRoute'
import { asSimulationId } from '@/contracts/runIdentifiers'

const props = defineProps<{
  reportId: string
}>()

// Die Route /v4/interaction/:reportId kennt nur die reportId. Chat, Interview
// und Profil-Liste brauchen aber die simulation_id. Issue #1023 (Regression
// aus PR #997): der frühere gemeinsame Query-Schlüssel `runId` transportierte
// hier faelschlich die Registry-Run-ID statt der simulation_id — beide sind
// unvereinbare ID-Räume (`run_…` vs. `sim_…`). Der eigene Schlüssel
// `simId` plus Formatpruefung stellt sicher, dass hier ausschliesslich eine
// echte Simulation-ID ankommt; fehlt sie oder passt das Format nicht, faellt
// Step5Interaction auf die simulation_id aus dem geladenen Report zurueck.
const route = useRoute()
const simulationIdFromQuery = computed<string | null>(() => {
  const value = route.query[INTERACTION_SIMULATION_ID_QUERY_KEY]
  return asSimulationId(value)
})

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.reportId },
  { label: 'Interaktion' },
])
</script>
