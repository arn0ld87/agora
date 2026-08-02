<!--
  StepGraphBuildView — AppShell-Wrapper fuer Step 1 (Graph-Build / Upload).
  Der Inhalt (Step1GraphBuild.vue) bleibt v2-typografiert — Inhalts-Migration
  ist ein eigener Folge-Slice.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      :title="$t('views.stepGraphBuild.title')"
      :subtitle="$t('views.stepGraphBuild.subtitle')"
    >
      <template #right>
        <StepModelOverrideChip stage-id="graph_build" :run-id="currentRunId" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="1" />
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="graph-build-layout">
      <!-- Wissensgraph-Canvas: sichtbar sobald graphData geladen ist (Phase 2). -->
      <section v-if="graphData" class="graph-build-canvas">
        <GraphPanel
          :graph-data="graphData"
          :loading="graphLoading"
          :current-phase="currentPhase"
        />
      </section>
      <Step1GraphBuild
        :currentPhase="currentPhase"
        :projectData="projectData"
        :ontologyProgress="ontologyProgress"
        :buildProgress="buildProgress"
        :graphData="graphData"
        :systemLogs="systemLogs"
        @next-step="handleNextStep"
      />
    </div>
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
import GraphPanel from '@/components/GraphPanel.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import { useGraphBuildPipeline } from '@/composables/useGraphBuildPipeline'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()
const { t } = useI18n()

function handleNextStep(): void {
  void router.push({
    name: 'StepEnvSetup',
    params: { projectId: props.projectId },
  })
}
const {
  projectData,
  currentProjectId,
  currentPhase,
  ontologyProgress,
  buildProgress,
  graphData,
  graphLoading,
  systemLogs,
  error,
  currentRunId,
  initialize,
} = useGraphBuildPipeline({ projectId: props.projectId, router, t })

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('step1.breadcrumbRuns'), path: '/runs' },
  { label: props.projectId },
  { label: t('step1.breadcrumbTitle') },
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

<style scoped>
.graph-build-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* GraphPanel rendert absolut/height:100% — braucht eine dimensionierte Buehne. */
.graph-build-canvas {
  position: relative;
  width: 100%;
  height: clamp(360px, 55vh, 640px);
  border: 1px solid var(--hairline, var(--mono-700));
  border-radius: 8px;
  overflow: hidden;
}
</style>
