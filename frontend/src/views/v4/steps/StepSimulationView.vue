<!--
  StepSimulationView — Pipeline-Tab-Inhalt der Simulation (Kind-Route von
  SimulationLayout.vue).

  Fix #1713: Kopfzeile, Breadcrumbs, Stepper und Tabs sind in
  SimulationLayout.vue gewandert — diese View ist nur noch der
  Pipeline-Inhalt, analog zu StepSimulationFeedView.vue.
-->
<template>
  <Step3Simulation
    :simulation-id="simulationId"
    :max-rounds="runParams.maxRounds ?? undefined"
    :simulation-days="runParams.simulationDays ?? undefined"
    :budget="runParams.budget ?? undefined"
    @go-back="handleGoBack"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Step3Simulation from '@/components/v4/steps/Step3Simulation.vue'
import { readRunParamsFromQuery } from '@/contracts/runParamsQuery'

const props = defineProps<{
  simulationId: string
}>()

const route = useRoute()
const router = useRouter()

// Runden/Tage aus Step 2 stehen in der Query: ``props: true`` reicht nur
// Route-Params durch. Die Query überlebt zusätzlich einen Reload auf dieser
// Route — anders als der pendingUpload-Store, der dem Dashboard-Start gehört.
const runParams = computed(() => readRunParamsFromQuery(route.query))

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
</script>
