<!--
  StepSimulationView — AppShell-Wrapper fuer Step 3 (Simulation).
  Tab-Switch: Pipeline (existing) vs. Live-Feed (Slice 5).
  Slice FE-Redesign-5 · 2026-05-15
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader
      title="Simulation"
      subtitle="Multi-Agent-Simulationslauf starten und beobachten"
    >
      <template #right>
        <StepModelOverrideChip stage-id="simulation_rounds" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="3" />

    <Tabs
      v-model="activeTab"
      :tabs="tabItems"
      :url-sync="false"
      class="sim-view-tabs"
    />

    <div class="sim-view-content">
      <Step3Simulation v-if="activeTab === 'pipeline'" :simulation-id="simulationId" />
      <RouterView v-else-if="activeTab === 'feed'" />
      <StepSimulationFeedView
        v-if="activeTab === 'feed'"
        :simulation-id="simulationId"
      />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step3Simulation from '@/components/Step3Simulation.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import Tabs from '@/components/v4/data/Tabs.vue'
import StepSimulationFeedView from './StepSimulationFeedView.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import type { TabItem } from '@/components/v4/data/Tabs.vue'

const props = defineProps<{
  simulationId: string
}>()

const { t } = useI18n()

const activeTab = ref<string>('pipeline')

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
