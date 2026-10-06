<script setup lang="ts">
/**
 * Feed der Simulation. Übergangshülle (Etappe 4, #1801): bettet die bestehende
 * Feed-Ansicht ein, bis die neue Oberfläche steht. Die Altansicht liest
 * `route.params.simulationId` und `route.query`; beides gibt es auch hier.
 * `network` (`twitter|reddit`) wird von der neuen Oberfläche ausgewertet.
 */
import StepSimulationFeedView from '@/views/v4/steps/StepSimulationFeedView.vue'

defineProps<{ simulationId: string; network?: string }>()
</script>

<template>
  <StepSimulationFeedView />
</template>
