<!--
  StepEnvSetupView — AppShell-Wrapper fuer Step 2 (Persona-Quoten / Env-Setup).
  Der Inhalt (Step2EnvSetup.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
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
    <Step2EnvSetup :simulation-id="projectId" />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step2EnvSetup from '@/components/Step2EnvSetup.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  projectId: string
}>()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.projectId },
  { label: 'Personas' },
])
</script>
