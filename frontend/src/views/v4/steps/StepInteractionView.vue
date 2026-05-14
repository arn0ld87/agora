<!--
  StepInteractionView — AppShell-Wrapper fuer Step 5 (Interaktion).
  Der Inhalt (Step5Interaction.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Interaktion"
      subtitle="Gezielte Nachfragen an die simulierten Personas stellen"
    />
    <PipelineStepper :current-step="5" />
    <Step5Interaction :report-id="reportId" />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step5Interaction from '@/components/Step5Interaction.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  reportId: string
}>()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.reportId },
  { label: 'Interaktion' },
])
</script>
