<!--
  SimulationLayout — gemeinsame Huelle fuer Schritt 3 (Simulation): Kopf,
  Breadcrumbs, Tabs (Pipeline | Feed | Diskurs | Runden | Protokoll) und der
  aktive Tab-Inhalt ueber RouterView.

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

  Slice UI-2b (docs/design/simulation-feed.md §1): drei weitere Kind-Routen
  (Diskurs/Strang, Runden, Protokoll) kommen dazu. SimTabsBar ersetzt die
  bisherige `Tabs`-Instanz und navigiert selbststaendig; `activeTab` schaut
  jetzt auf einen Namens-Prefix (SimThreads/SimThreadFocus → 'threads').
-->
<template>
  <div>
    <PageHeader :title="headerTitle" :subtitle="headerSubtitle">
      <template v-if="activeTab === 'pipeline'" #right>
        <StepModelOverrideChip stage-id="simulation_rounds" />
      </template>
    </PageHeader>
    <PipelineStepper :current-step="3" />

    <SimTabsBar :active-tab="activeTab" :simulation-id="simulationId" />

    <div class="sim-view-content">
      <RouterView />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import SimTabsBar, { type SimTabKey } from '@/components/v4/sim-feed/SimTabsBar.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { getSimulation } from '@/api/simulation'
import { unwrap } from '@/api/envelope'
import { clearSimFeed } from '@/composables/useSimFeed'
import { clearSimClock } from '@/composables/useSimClock'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'

const props = defineProps<{
  simulationId: string
}>()

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const activeTab = computed<SimTabKey>(() => {
  const name = String(route.name ?? '')
  if (name === 'StepSimulationFeed') return 'feed'
  // SimThreads und SimThreadFocus teilen sich den Diskurs-Tab.
  if (name.startsWith('SimThread')) return 'threads'
  if (name === 'SimRounds') return 'rounds'
  if (name === 'SimActions') return 'actions'
  return 'pipeline'
})

const TITLE_KEYS: Record<SimTabKey, string> = {
  pipeline: 'views.stepSimulation',
  feed: 'views.stepSimulationFeed',
  threads: 'views.simThreads',
  rounds: 'views.simRounds',
  actions: 'views.simActions',
}

const headerTitle = computed(() => t(`${TITLE_KEYS[activeTab.value]}.title`))
const headerSubtitle = computed(() => t(`${TITLE_KEYS[activeTab.value]}.subtitle`))

const TAB_LABEL_KEYS: Record<SimTabKey, string> = {
  pipeline: 'views.stepSimulation.title',
  feed: 'feed.feedTab',
  threads: 'feed.threadsTab',
  rounds: 'feed.roundsTab',
  actions: 'feed.actionsTab',
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
    { label: t(TAB_LABEL_KEYS[activeTab.value]) },
  ]
})

// Fix #1713 (Befund 5, Regression von #1007): gehoert an das Verlassen der
// gesamten Simulation, nicht an den Tab-Wechsel (siehe Step3Simulation.vue).
onBeforeUnmount(() => {
  clearSimFeed(props.simulationId)
  clearSimClock(props.simulationId)
})

useShellBreadcrumbs(crumbs)
</script>

<style scoped>
.sim-view-content {
  margin-top: 16px;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}
</style>
