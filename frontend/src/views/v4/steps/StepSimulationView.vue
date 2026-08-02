<!--
  StepSimulationView — AppShell-Wrapper fuer Step 3 (Simulation).
  Tab-Switch: Pipeline (existing) vs. Live-Feed (Slice 5).

  Fix #7: Feed-Tab navigiert via router.push zur eigenen Route StepSimulationFeed.
  StepSimulationFeedView wird NICHT direkt hier gerendert — kein Double-Mount,
  kein doppelter SSE-Stream.
  Active-Tab wird aus $route.name abgeleitet, kein lokales ref nötig.

  Slice FE-Redesign-5 · 2026-05-15
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      :title="$t('views.stepSimulation.title')"
      :subtitle="$t('views.stepSimulation.subtitle')"
    >
      <template #right>
        <StepModelOverrideChip stage-id="simulation_rounds" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="3" />

    <Tabs
      :model-value="activeTab"
      :tabs="tabItems"
      :url-sync="false"
      class="sim-view-tabs"
      @update:model-value="onTabChange"
    />

    <div class="sim-view-content">
      <Step3Simulation
        v-if="activeTab === 'pipeline'"
        :simulation-id="simulationId"
        :max-rounds="runParams.maxRounds ?? undefined"
        :simulation-days="runParams.simulationDays ?? undefined"
        @go-back="handleGoBack"
      />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step3Simulation from '@/components/v4/steps/Step3Simulation.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import Tabs from '@/components/v4/data/Tabs.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import type { TabItem } from '@/components/v4/data/Tabs.vue'
import { readRunParamsFromQuery } from '@/contracts/runParamsQuery'

const props = defineProps<{
  simulationId: string
}>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

// Active-Tab aus Route-Name ableiten — kein lokales ref, kein Sync-Problem.
const activeTab = computed<string>(() =>
  route.name === 'StepSimulationFeed' ? 'feed' : 'pipeline',
)

// Runden/Tage aus Step 2 stehen in der Query: ``props: true`` reicht nur
// Route-Params durch. Die Query überlebt zusätzlich einen Reload auf dieser
// Route — anders als der pendingUpload-Store, der dem Dashboard-Start gehört.
const runParams = computed(() => readRunParamsFromQuery(route.query))

function onTabChange(tab: string): void {
  // Query mitnehmen: sie trägt projectId (Voraussetzung für handleGoBack) und
  // die Run-Parameter. Ohne sie verlor ein Tab-Wechsel beides.
  const query = route.query
  if (tab === 'feed') {
    router.push({
      name: 'StepSimulationFeed',
      params: { simulationId: props.simulationId },
      query,
    })
  } else {
    router.push({
      name: 'StepSimulation',
      params: { simulationId: props.simulationId },
      query,
    })
  }
}

function handleGoBack(): void {
  const projectId = route.query.projectId
  if (typeof projectId !== 'string' || projectId.length === 0) {
    return
  }
  void router.push({
    name: 'StepEnvSetup',
    params: { projectId },
  })
}

const tabItems = computed<TabItem[]>(() => [
  { key: 'pipeline', label: t('feed.pipeline') },
  { key: 'feed', label: t('feed.feedTab') },
])

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.simulationId },
  { label: 'Simulation' },
])
</script>

<style scoped>
.sim-view-tabs {
  margin-bottom: 0;
}
.sim-view-content {
  margin-top: 16px;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}
</style>
