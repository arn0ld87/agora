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
    <!--
      Issue #1029: Ein Build kann durchlaufen und trotzdem ein Ergebnis
      liefern, mit dem weiterzuarbeiten sich nicht lohnt. Der Hinweis steht
      bewusst oberhalb des Canvas — er ist die Antwort auf „warum sieht der
      Graph so leer aus", nicht eine Fußnote darunter.
    -->
    <DegradationNotice :report="degradations" />
    <div class="graph-build-layout">
      <!-- Wissensgraph-Canvas: sichtbar sobald graphData geladen ist (Phase 2). -->
      <section v-if="graphData" class="graph-build-canvas">
        <GraphPanel
          :graph-data="graphData"
          :loading="graphLoading"
          :current-phase="currentPhase"
          :is-maximized="isGraphMaximized"
          @refresh="refreshGraph"
          @toggle-maximize="isGraphMaximized = !isGraphMaximized"
        />
      </section>
      <Step1GraphBuild
        :currentPhase="currentPhase"
        :projectData="projectData"
        :ontologyProgress="ontologyProgress"
        :buildProgress="buildProgress"
        :graphData="graphData"
        :systemLogs="systemLogs"
        :qualityBlocked="qualityBlocked"
        @next-step="handleNextStep"
      />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step1GraphBuild from '@/components/Step1GraphBuild.vue'
import GraphPanel from '@/components/GraphPanel.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import DegradationNotice from '@/components/v4/DegradationNotice.vue'
import { useGraphBuildPipeline } from '@/composables/useGraphBuildPipeline'
import { hasBlockingDegradation } from '@/contracts/pipelineDegradationContract'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  projectId: string
}>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// Der Dashboard-Start hängt Rundenzahl und Budget an die Route. Schritt 1
// verbraucht sie nicht, muss sie aber weiterreichen — sonst enden sie hier,
// weil der pendingUpload-Store nach dem Upload geleert wird (Issue #1234).
function handleNextStep(): void {
  void router.push({
    name: 'StepEnvSetup',
    params: { projectId: props.projectId },
    query: { ...route.query },
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
  degradations,
  graphIncomplete,
  initialize,
  refreshGraph,
} = useGraphBuildPipeline({
  projectId: props.projectId,
  router,
  t,
  preserveQuery: computed(() => ({ ...route.query })),
})

// Issue #1023 (Befund B-08): GraphToolbar emittiert toggle-maximize seit
// jeher, ohne dass irgendein Consumer zuhoert. CSS-Vollbild-Toggle statt
// Fullscreen-API (kein requestFullscreen im Repo) — GraphPanel wendet die
// entsprechende Klasse selbst an (siehe GraphPanel.vue).
const isGraphMaximized = ref(false)

// Issue #1029: Ein Graph unterhalb der Qualitätsschwelle hat den Build
// zwar überstanden, taugt aber nicht als Grundlage für die folgenden
// Schritte. „Bereit" bleibt deshalb aus, und der Weiter-Knopf ebenso.
// PR #1371: graphIncomplete blockiert genau wie ein Qualitaetsbefund —
// ein per Abbruch behaltener Teilgraph ist ansehbar, aber keine Grundlage
// fuer die folgenden Schritte.
const qualityBlocked = computed(() => hasBlockingDegradation(degradations.value) || graphIncomplete.value)

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
  border: 1px solid var(--hairline);
  border-radius: 8px;
  overflow: hidden;
}
</style>
