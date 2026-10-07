<script setup lang="ts">
/**
 * Neuer Lauf (#1799, Etappe 3): dünne Hülle um den Startdialog. Die Route
 * `/library/runs/new` (Name `NewRun`) trägt `meta.windowOverBackground`; App.vue
 * rendert darunter die zuletzt gezeigte Ansicht, diese Komponente ist das Fenster.
 */
import NewRunDialog from '@/components/new-run/NewRunDialog.vue'
</script>

<template>
  <NewRunDialog />
</template>
