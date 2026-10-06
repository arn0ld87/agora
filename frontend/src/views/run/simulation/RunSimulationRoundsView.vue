<script setup lang="ts">
/**
 * Runden der Simulation. Übergangshülle (Etappe 4, #1801): bettet die
 * bestehende Runden-Ansicht ein, bis die neue Oberfläche steht.
 */
import SimRoundsView from '@/views/v4/steps/SimRoundsView.vue'

defineProps<{ simulationId: string }>()
</script>

<template>
  <SimRoundsView />
</template>
