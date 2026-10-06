<script setup lang="ts">
/**
 * Beitrag (Faden-Ansicht) der Simulation. Übergangshülle (Etappe 4, #1801):
 * bettet die bestehende Strang-Ansicht ein. `postId` kann Doppelpunkte
 * enthalten (`twitter:123`, `reddit:comment:7`) und wird unverändert gereicht.
 */
import SimThreadFocusView from '@/views/v4/steps/SimThreadFocusView.vue'

defineProps<{ simulationId: string; postId: string }>()
</script>

<template>
  <SimThreadFocusView :post-id="postId" />
</template>
