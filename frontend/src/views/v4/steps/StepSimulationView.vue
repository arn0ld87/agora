<!--
  StepSimulationView — AppShell-Wrapper fuer Step 3 (Simulation).
  Der Inhalt (Step3Simulation.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Simulation"
      subtitle="Multi-Agent-Simulationslauf starten und beobachten"
    />
    <PipelineStepper :current-step="3" />
    <Step3Simulation :simulation-id="simulationId" />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step3Simulation from '@/components/Step3Simulation.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  simulationId: string
}>()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.simulationId },
  { label: 'Simulation' },
])
</script>
