<script setup lang="ts">
/**
 * Simulation als Reiter am Lauf (Etappe 4, #1801, Bauplan 4.5): Hülle mit den
 * Unterreitern Feed · Runden · Diagnose, dem Simulationskopf und der Kind-Ansicht.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import RunSimHeader from '@/components/run/simulation/RunSimHeader.vue'
import { usePersonasReady } from '@/composables/run/simulation/usePersonasReady'
import { provideSimulationRunState } from '@/composables/run/simulation/useSimulationRunStateContext'
import { useRunWorkspaceContext } from '@/composables/run/useRunWorkspace'

const props = defineProps<{ simulationId: string }>()
const { t } = useI18n()
const route = useRoute()

const workspace = useRunWorkspaceContext()
const personasReady = usePersonasReady()
const simulationJob = computed(() => workspace.data.value?.jobs.simulation_run ?? null)

// Eine Instanz für Kopf, Feed und Runden: ein SSE-Strom und ein Polling je Lauf.
provideSimulationRunState(() => props.simulationId, { runId: () => simulationJob.value?.runId ?? null })

/** Start, Stopp, Pause oder Fortsetzen ist durch: Stufenstand des Arbeitsbereichs neu laden. */
function reloadWorkspace(): void {
  void workspace.reload()
}

type SubTabKey = 'feed' | 'rounds' | 'diagnostics'

const SUB_TABS: { key: SubTabKey; name: string }[] = [
  { key: 'feed', name: 'RunSimulationFeed' },
  { key: 'rounds', name: 'RunSimulationRounds' },
  { key: 'diagnostics', name: 'RunSimulationDiagnostics' },
]

/** „Feed“ gilt auch auf der Beitragsadresse. */
const activeKey = computed<SubTabKey | null>(() => {
  switch (route.name) {
    case 'RunSimulationFeed':
    case 'RunSimulationPost':
      return 'feed'
    case 'RunSimulationRounds':
      return 'rounds'
    case 'RunSimulationDiagnostics':
      return 'diagnostics'
    default:
      return null
  }
})
</script>

<template>
  <div class="run-sim" data-testid="run-simulation">
    <nav class="run-sim__tabs" :aria-label="t('views.run.simulation.tabsLabel')" data-testid="run-sim-tabs">
      <router-link
        v-for="tab in SUB_TABS"
        :key="tab.key"
        v-slot="{ href, navigate }"
        custom
        :to="{ name: tab.name, params: { simulationId } }"
      >
        <a
          :href="href"
          class="run-sim__tab"
          :class="{ 'run-sim__tab--active': activeKey === tab.key }"
          :aria-current="activeKey === tab.key ? 'page' : undefined"
          :data-testid="`run-sim-tab-${tab.key}`"
          @click="navigate"
        >
          {{ t(`views.run.simulation.tab.${tab.key}`) }}
        </a>
      </router-link>
    </nav>

    <div
      role="region"
      :aria-label="t('views.run.simulation.headerSlotLabel')"
      data-testid="run-sim-header-slot"
    >
      <RunSimHeader
        :simulation-id="simulationId"
        :run-id="simulationJob?.runId ?? null"
        :route="simulationJob?.route ?? null"
        :personas-ready="personasReady"
        @started="reloadWorkspace"
        @changed="reloadWorkspace"
      />
    </div>

    <router-view />
  </div>
</template>

<style scoped>
.run-sim {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 12px;
}
.run-sim__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.run-sim__tab {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 12px;
  border-radius: var(--ag-r-8);
  color: var(--fg2);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
}
.run-sim__tab:hover {
  background: var(--s2);
  color: var(--fg);
}
.run-sim__tab:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.run-sim__tab--active {
  background: var(--s3);
  color: var(--fg);
  font-weight: 650;
}
</style>
