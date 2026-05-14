<template>
  <div class="graph-panel">
    <GraphToolbar
      :loading="loading"
      :has-graph-id="!!graphData?.graph_id"
      :has-graph-data="!!graphData"
      :is-paused="canvasRef?.isPaused?.value === true"
      @refresh="$emit('refresh')"
      @toggle-maximize="$emit('toggle-maximize')"
      @toggle-pause="canvasRef?.togglePause()"
      @download-graphml="canvasRef?.downloadGraphml()"
      @download-svg="canvasRef?.downloadSvg()"
      @download-png="canvasRef?.downloadPng()"
      @print-pdf="canvasRef?.printPdf()"
    />

    <GraphCanvas
      ref="canvasRef"
      :graph-data="displayedGraphData"
      :entity-types="entityTypes"
      :loading="loading"
      :current-phase="currentPhase"
      :is-simulating="isSimulating"
      :show-finished-hint="showSimulationFinishedHint"
      :batch-signal="batchSignal"
      @dismiss-finished-hint="dismissFinishedHint"
    />

    <GraphLegend v-if="graphData && entityTypes.length" :entity-types="entityTypes" />

    <!-- Issue #10 — Temporal-Round-Slider (only visible once the graph carries simulation rounds) -->
    <GraphRoundSlider
      v-if="graphData && maxRound > 0"
      v-model="selectedRound"
      :max-round="maxRound"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

import GraphCanvas from './graph/GraphCanvas.vue'
import GraphLegend from './graph/GraphLegend.vue'
import GraphRoundSlider from './graph/GraphRoundSlider.vue'
import GraphToolbar from './graph/GraphToolbar.vue'
import { filterEdgesAtRound, getMaxRoundFromEdges } from './graph/graphPanelData'
import { buildEntityTypes } from './graph/graphPanelUtils'

const props = defineProps({
  graphData: Object,
  loading: Boolean,
  currentPhase: Number,
  isSimulating: Boolean,
  // Issue #137 SUB2 — batch progress signal forwarded from MainView polling.
  // Passed through to GraphCanvas → useGraphRender for Auto-Freeze.
  batchSignal: { type: Object, default: null },
})

defineEmits(['refresh', 'toggle-maximize'])

const canvasRef = ref(null)

// Issue #10 — Temporal-Slider state. null means "live" (= maxRound, all current edges).
const selectedRound = ref(null)
const showSimulationFinishedHint = ref(false)
const wasSimulating = ref(false)

const maxRound = computed(() => getMaxRoundFromEdges(props.graphData?.edges))
const entityTypes = computed(() => buildEntityTypes(props.graphData))

const displayedGraphData = computed(() => {
  if (!props.graphData) return null
  if (selectedRound.value == null) return props.graphData
  return {
    ...props.graphData,
    edges: filterEdgesAtRound(props.graphData.edges, selectedRound.value),
  }
})

const dismissFinishedHint = () => {
  showSimulationFinishedHint.value = false
}

// Watch isSimulating change, detect simulation end
watch(() => props.isSimulating, (newValue) => {
  if (wasSimulating.value && !newValue) {
    showSimulationFinishedHint.value = true
  }
  wasSimulating.value = newValue
}, { immediate: true })
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: var(--surface-elevated, var(--bg-elevated));
  background-image: radial-gradient(var(--hairline-strong, var(--mono-700)) 1px, transparent 1px);
  background-size: 24px 24px;
  overflow: hidden;
}
</style>
