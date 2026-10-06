<script setup lang="ts">
/**
 * Diagnose der Simulation. Platzhalter (Etappe 4, #1801), bis die gefilterte
 * Konsole eingebaut ist.
 */
import { useI18n } from 'vue-i18n'

defineProps<{ simulationId: string }>()
const { t } = useI18n()
</script>

<template>
  <section data-testid="run-sim-diagnostics">
    <h2>{{ t('views.run.simulation.diagnostics.title') }}</h2>
    <p role="status">{{ t('views.run.simulation.diagnostics.pending') }}</p>
  </section>
</template>
