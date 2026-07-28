<!--
  StepReportView — AppShell-Wrapper fuer Step 4 (Report).
  Der Inhalt (Step4Report.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      :title="$t('views.stepReport.title')"
      :subtitle="$t('views.stepReport.subtitle')"
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
import Step4Report from '@/components/Step4Report.vue'
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
