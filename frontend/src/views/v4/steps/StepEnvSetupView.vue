<!--
  StepEnvSetupView — AppShell-Wrapper fuer Step 2 (Persona-Quoten / Env-Setup).
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Personas"
      subtitle="Zielgruppenquoten und Umgebungsparameter konfigurieren"
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

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.projectId },
  { label: 'Personas' },
])

function handleNextStep(payload: { simulationId?: unknown }): void {
  if (typeof payload?.simulationId !== 'string' || payload.simulationId.length === 0) {
    return
  }
  void router.push({
    name: 'StepSimulation',
    params: { simulationId: payload.simulationId },
    query: { projectId: props.projectId },
  })
}

function handleGoBack(): void {
  void router.push({
    name: 'StepGraphBuild',
    params: { projectId: props.projectId },
  })
}
</script>
