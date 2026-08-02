<!--
  StepEnvSetupView — AppShell-Wrapper fuer Step 2 (Persona-Quoten / Env-Setup).
-->
<template>
  <AppShell :breadcrumbs="crumbs">
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
      :simulation-id="projectId"
      @next-step="handleNextStep"
      @go-back="handleGoBack"
    />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step2EnvSetup from '@/components/v4/steps/Step2EnvSetup.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { toRunParamsQuery } from '@/contracts/runParamsQuery'

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.projectId },
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
  // überstimmt hat. Sie müssen in die Query: die Route hat ``props: true``,
  // das überträgt ausschließlich Route-Params — vorher gingen die Werte hier
  // verloren und Step 3 startete stets mit dem Auto-Wert (B-09/B-27).
  void router.push({
    name: 'StepSimulation',
    params: { simulationId: payload.simulationId },
    query: { projectId: props.projectId, ...toRunParamsQuery(payload) },
  })
}

function handleGoBack(): void {
  void router.push({
    name: 'StepGraphBuild',
    params: { projectId: props.projectId },
  })
}
</script>
