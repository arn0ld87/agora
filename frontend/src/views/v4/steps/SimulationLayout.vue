<!--
  SimulationLayout — gemeinsame Huelle fuer Schritt 3 (Simulation): Kopf,
  Breadcrumbs, Tabs (Pipeline | Live-Feed) und der aktive Tab-Inhalt ueber
  RouterView.

  Fix #1713 (Befund 2): der Feed-Tab war zuvor nur eine `activeTab`-Weiche in
  StepSimulationView, die Route selbst (StepSimulationFeed) blieb tot. Jetzt
  sind Pipeline und Feed echte Kind-Routen dieses Layouts — beide Tabs sind
  eigenstaendig aufrufbare URLs mit funktionierendem Browser-Back.

  Fix #1713 (Befund 3/4): Run-Parameter kommen aus der Query. Fehlt
  `projectId` (Einstieg aus der Ablage ueber useShelf.ts::nextActionFor oder
  ein Deep-Link ohne Query), wird es einmalig ueber getSimulation()
  nachgeladen und per router.replace() in die Query geschrieben, statt den
  Rueckweg (handleGoBack in StepSimulationView) still abzubrechen.

  Fix #1713 (Befund 5, Regression von #1007): clearSimFeed/clearSimClock
  laufen nur noch hier, beim Verlassen der gesamten Simulation — nicht mehr
  bei jedem Tab-Wechsel (siehe Step3Simulation.vue).
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader :title="headerTitle" :subtitle="headerSubtitle">
      <template v-if="activeTab === 'pipeline'" #right>
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
      <RouterView />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import Tabs from '@/components/v4/data/Tabs.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import type { TabItem } from '@/components/v4/data/Tabs.vue'
import { getSimulation } from '@/api/simulation'
import { unwrap } from '@/api/envelope'
import { clearSimFeed } from '@/composables/useSimFeed'
import { clearSimClock } from '@/composables/useSimClock'

const props = defineProps<{
  simulationId: string
}>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const activeTab = computed<string>(() =>
  route.name === 'StepSimulationFeed' ? 'feed' : 'pipeline',
)

const headerTitle = computed(() =>
  activeTab.value === 'feed'
    ? t('views.stepSimulationFeed.title')
    : t('views.stepSimulation.title'),
)
const headerSubtitle = computed(() =>
  activeTab.value === 'feed'
    ? t('views.stepSimulationFeed.subtitle')
    : t('views.stepSimulation.subtitle'),
)

const tabItems = computed<TabItem[]>(() => [
  { key: 'pipeline', label: t('feed.pipeline') },
  { key: 'feed', label: t('feed.feedTab') },
])

function onTabChange(tab: string): void {
  // Query mitnehmen: sie traegt projectId (Voraussetzung fuer handleGoBack)
  // und die Run-Parameter. Ohne sie verlor ein Tab-Wechsel beides.
  const query = route.query
  const name = tab === 'feed' ? 'StepSimulationFeed' : 'StepSimulation'
  void router.push({ name, params: { simulationId: props.simulationId }, query })
}

// Fix #1713 (Befund 3/4): fehlt projectId in der Query, einmalig nachladen
// statt den Rueckweg in den Kind-Views still abbrechen zu lassen.
const projectIdLookupDone = ref(false)

async function ensureProjectId(): Promise<void> {
  if (typeof route.query.projectId === 'string' && route.query.projectId.length > 0) {
    return
  }
  if (projectIdLookupDone.value) return
  projectIdLookupDone.value = true
  try {
    const record = unwrap(await getSimulation(props.simulationId))
    const projectId = record.project_id
    if (typeof projectId === 'string' && projectId.length > 0) {
      void router.replace({ query: { ...route.query, projectId } })
    }
  } catch {
    // Best-effort: ohne aufloesbare Simulation gibt es ohnehin kein
    // sinnvolles Rueckweg-Ziel; handleGoBack bricht dann weiterhin ab.
  }
}

onMounted(() => {
  void ensureProjectId()
})

function withCurrentQuery(path: string): string {
  const entries = Object.entries(route.query).filter(
    (entry): entry is [string, string] => typeof entry[1] === 'string',
  )
  const qs = new URLSearchParams(entries).toString()
  return qs.length > 0 ? `${path}?${qs}` : path
}

const crumbs = computed<BreadcrumbItem[]>(() => {
  const pipelinePath = router.resolve({
    name: 'StepSimulation',
    params: { simulationId: props.simulationId },
  }).path
  return [
    { label: 'Runs', path: '/runs' },
    { label: props.simulationId, path: withCurrentQuery(pipelinePath) },
    { label: activeTab.value === 'feed' ? t('feed.feedTab') : t('views.stepSimulation.title') },
  ]
})

// Fix #1713 (Befund 5, Regression von #1007): gehoert an das Verlassen der
// gesamten Simulation, nicht an den Tab-Wechsel (siehe Step3Simulation.vue).
onBeforeUnmount(() => {
  clearSimFeed(props.simulationId)
  clearSimClock(props.simulationId)
})
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
