<!--
  StepReportView — AppShell-Wrapper fuer Step 4 (Report).
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Report"
      subtitle="Simulationsergebnisse und Quellenbelege einsehen"
    >
      <template #right>
        <StepModelOverrideChip stage-id="report_generation" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="4" />
    <Step4Report :report-id="reportId" />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step4Report from '@/components/v4/steps/Step4Report.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  reportId: string
}>()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.reportId },
  { label: 'Report' },
])
</script>
