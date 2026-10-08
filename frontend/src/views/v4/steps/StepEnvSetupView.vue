<!--
  StepEnvSetupView — AppShell-Wrapper fuer Step 2 (Persona-Quoten / Env-Setup).
-->
<template>
  <div>
    <PageHeader
      :title="$t('views.stepEnvSetup.title')"
      :subtitle="$t('views.stepEnvSetup.subtitle')"
    >
      <template #right>
        <StepModelOverrideChip stage-id="persona_generation" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="2" />
    <Step2EnvSetup
      :simulation-id="simulationId"
      @next-step="handleNextStep"
      @go-back="handleGoBack"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step2EnvSetup from '@/components/v4/steps/Step2EnvSetup.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { readRunParamsFromQuery, toRunParamsQuery } from '@/contracts/runParamsQuery'
import { readPendingRunParams, writePendingRunParams } from '@/composables/new-run/pendingRunParams'
import { crumbForId, useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'

const props = defineProps<{
  projectId: string
}>()

const route = useRoute()
const router = useRouter()
const simulationId = computed(() => {
  const querySimulationId = route.query.simulationId
  return typeof querySimulationId === 'string' && querySimulationId.length > 0
    ? querySimulationId
    : props.projectId
})

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/library/runs' },
  crumbForId(props.projectId),
  { label: 'Personas' },
])

function handleNextStep(payload: {
  simulationId?: unknown
  maxRounds?: unknown
  simulationDays?: unknown
}): void {
  if (typeof payload?.simulationId !== 'string' || payload.simulationId.length === 0) {
    return
  }
  // Step 2 sendet Runden/Tage nur, wenn der Nutzer den Auto-Vorschlag
  // überstimmt hat. Die Simulation am Lauf (#1801) liest ihre Startwerte aus
  // den vorgemerkten Startparametern (`pendingRunParams`), nicht aus der Adresse:
  // Hier landen sie dort, bevor wir auf den Feed des Laufs wechseln.
  //
  // Was schon in der Query steht, kommt vom Dashboard-Start und bleibt, sofern
  // Schritt 2 nichts Eigenes dazu sagt (Issue #1234); ein früher vorgemerkter
  // Eintrag bleibt, wo beide nichts sagen. Das Budget kennt Schritt 2 gar nicht.
  const simulationId = payload.simulationId
  const inherited = readRunParamsFromQuery(route.query)
  const earlier = readPendingRunParams(simulationId)
  // Die Werte laufen durch dieselbe Validierung wie in der Query (Bereichsgrenzen).
  const merged = readRunParamsFromQuery(
    toRunParamsQuery({
      maxRounds: payload.maxRounds ?? inherited.maxRounds ?? earlier?.maxRounds,
      simulationDays: payload.simulationDays ?? inherited.simulationDays ?? earlier?.simulationDays,
      budget: inherited.budget ?? earlier?.budget,
    }),
  )
  writePendingRunParams(simulationId, {
    maxRounds: merged.maxRounds,
    simulationDays: merged.simulationDays,
    budget: merged.budget,
  })
  void router.push({ name: 'RunSimulationFeed', params: { simulationId } })
}

function handleGoBack(): void {
  void router.push({
    name: 'StepGraphBuild',
    params: { projectId: props.projectId },
    query: { ...route.query },
  })
}

useShellBreadcrumbs(crumbs)
</script>
