<!--
  StepReportView — AppShell-Wrapper fuer Step 4 (Report).
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
    <Step4Report :report-id="reportId" :run-id="runIdFromQuery ?? undefined" />
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step4Report from '@/components/v4/steps/Step4Report.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  reportId: string
}>()

// Issue #764 (Codex P1): run_id wird vom uebergeordneten Step3 als
// Query-Param ?runId=... weitergereicht, damit Step4Report.loadRunUsage
// die Registry-eindeutige ID statt simulation_id fuer /api/runs/<id>
// verwendet. Fehlt der Param (z.B. Direktaufruf der Report-Route),
// bleibt die Legacy-Aufloesung ueber simulationId aktiv.
const route = useRoute()
const runIdFromQuery = computed<string | null>(() => {
  const value = route.query.runId
  return typeof value === 'string' && value.length > 0 ? value : null
})

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.reportId },
  { label: 'Report' },
])
</script>
