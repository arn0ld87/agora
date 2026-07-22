<!--
  StepGraphBuildView — AppShell-Wrapper fuer Step 1 (Graph-Build / Upload).
  Der Inhalt (Step1GraphBuild.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Graph Build"
      subtitle="Wissensgraph aus hochgeladenen Dokumenten aufbauen"
    >
      <template #right>
        <StepModelOverrideChip stage-id="graph_build" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="1" />
    <p v-if="error" role="alert">{{ error }}</p>
    <Step1GraphBuild
      :currentPhase="currentPhase"
      :projectData="projectData"
      :ontologyProgress="ontologyProgress"
      :buildProgress="buildProgress"
      :graphData="graphData"
      :systemLogs="systemLogs"
    />
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step1GraphBuild from '@/components/Step1GraphBuild.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import { useGraphBuildPipeline } from '@/composables/useGraphBuildPipeline'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()
const { t } = useI18n()
const {
  projectData,
  currentProjectId,
  currentPhase,
  ontologyProgress,
  buildProgress,
  graphData,
  systemLogs,
  error,
  initialize,
} = useGraphBuildPipeline({ projectId: props.projectId, router, t })

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.projectId },
  { label: 'Graph Build' },
])

onMounted(() => {
  void initialize()
})

watch(
  () => props.projectId,
  (nextProjectId) => {
    if (nextProjectId !== currentProjectId.value) {
      void initialize(nextProjectId)
    }
  },
)
</script>
