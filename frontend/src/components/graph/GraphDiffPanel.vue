<template>
  <div class="diff-panel">
    <!-- Top-Bar mit Snapshot-Selektoren und Statistik-Strip -->
    <header class="diff-toolbar">
      <div class="diff-selectors">
        <label class="diff-selector-label">
          {{ t('graphDiff.snapshotA') }}
          <select v-model="selectedA" class="diff-select">
            <option value="" disabled>—</option>
            <option
              v-for="snap in availableSnapshots"
              :key="snap.id"
              :value="snap.id"
            >
              {{ snap.label }}
            </option>
          </select>
        </label>
        <span class="diff-arrow">→</span>
        <label class="diff-selector-label">
          {{ t('graphDiff.snapshotB') }}
          <select v-model="selectedB" class="diff-select">
            <option value="" disabled>—</option>
            <option
              v-for="snap in availableSnapshots"
              :key="snap.id"
              :value="snap.id"
            >
              {{ snap.label }}
            </option>
          </select>
        </label>
      </div>

      <!-- Statistik-Strip (nur wenn Diff vorhanden) -->
      <div v-if="diff" class="diff-stats">
        <span class="diff-stat">
          <span class="diff-stat-label">{{ t('graphDiff.statsNodes') }}</span>
          <span class="diff-stat-value" :class="deltaClass(nodeDelta)">
            {{ formatDelta(nodeDelta) }}
          </span>
        </span>
        <span class="diff-stat">
          <span class="diff-stat-label">{{ t('graphDiff.statsEdges') }}</span>
          <span class="diff-stat-value" :class="deltaClass(edgeDelta)">
            {{ formatDelta(edgeDelta) }}
          </span>
        </span>
        <span class="diff-stat">
          <span class="diff-stat-label">{{ t('graphDiff.statsClusters') }}</span>
          <span class="diff-stat-value" :class="deltaClass(clusterDelta)">
            {{ formatDelta(clusterDelta) }}
          </span>
        </span>
        <span class="diff-stat">
          <span class="diff-stat-label">{{ t('graphDiff.statsDensity') }}</span>
          <span class="diff-stat-value" :class="deltaClass(diff.metrics.density_delta)">
            {{ formatDeltaFloat(diff.metrics.density_delta) }}
          </span>
        </span>
      </div>
    </header>

    <!-- Empty-State: gleiche Snapshots gewählt -->
    <div v-if="isSameSnapshot" class="diff-empty">
      <p>{{ t('graphDiff.empty.sameSnapshots') }}</p>
    </div>

    <!-- Loading-State -->
    <div v-else-if="loading" class="diff-loading">
      <div class="diff-spinner"></div>
      <p>{{ t('graphDiff.loading') }}</p>
    </div>

    <!-- Error-State -->
    <div v-else-if="error" class="diff-error" role="alert">
      <p>{{ t('graphDiff.error.generic') }}: {{ error }}</p>
    </div>

    <!-- Hauptinhalt: Diff-Ansicht -->
    <div v-else-if="diff" class="diff-body">
      <!-- Legende -->
      <div class="diff-legend">
        <span class="legend-item diff-added">{{ t('graphDiff.legend.added') }}</span>
        <span class="legend-item diff-removed">{{ t('graphDiff.legend.removed') }}</span>
        <span class="legend-item diff-reinforced">{{ t('graphDiff.legend.reinforced') }}</span>
        <span class="legend-item diff-weakened">{{ t('graphDiff.legend.weakened') }}</span>
      </div>

      <!-- Zweispaltige Graph-Ansicht -->
      <div class="diff-columns">
        <div class="diff-column">
          <div class="diff-column-header">{{ diff.snapshot_a.snapshot_id ?? diff.snapshot_a_id }}</div>
          <div class="diff-canvas-wrap">
            <GraphCanvas
              :graph-data="snapshotAGraphData ?? undefined"
              :entity-types="[]"
              :loading="false"
            />
          </div>
        </div>
        <div class="diff-column">
          <div class="diff-column-header">{{ diff.snapshot_b.snapshot_id ?? diff.snapshot_b_id }}</div>
          <div class="diff-canvas-wrap">
            <GraphCanvas
              :graph-data="snapshotBGraphData ?? undefined"
              :entity-types="[]"
              :loading="false"
            />
          </div>
        </div>
      </div>

      <!-- Diff-Annotationen (Edge-Klassifizierung) -->
      <div class="diff-edge-summary">
        <div v-if="diff.edges_added.length > 0" class="diff-edge-group">
          <h4 class="diff-edge-group-title diff-added">
            {{ t('graphDiff.legend.added') }} ({{ diff.edges_added.length }})
          </h4>
          <ul class="diff-edge-list">
            <li v-for="edge in diff.edges_added" :key="edge.uuid" class="diff-edge-item diff-added">
              {{ edge.source_id }} → {{ edge.target_id }}
              <span class="diff-edge-type">{{ edge.relation_type }}</span>
            </li>
          </ul>
        </div>
        <div v-if="diff.edges_removed.length > 0" class="diff-edge-group">
          <h4 class="diff-edge-group-title diff-removed">
            {{ t('graphDiff.legend.removed') }} ({{ diff.edges_removed.length }})
          </h4>
          <ul class="diff-edge-list">
            <li v-for="edge in diff.edges_removed" :key="edge.uuid" class="diff-edge-item diff-removed">
              {{ edge.source_id }} → {{ edge.target_id }}
              <span class="diff-edge-type">{{ edge.relation_type }}</span>
            </li>
          </ul>
        </div>
        <div v-if="diff.edges_reinforced.length > 0" class="diff-edge-group">
          <h4 class="diff-edge-group-title diff-reinforced">
            {{ t('graphDiff.legend.reinforced') }} ({{ diff.edges_reinforced.length }})
          </h4>
          <ul class="diff-edge-list">
            <li v-for="er in diff.edges_reinforced" :key="er.edge.uuid" class="diff-edge-item diff-reinforced">
              {{ er.edge.source_id }} → {{ er.edge.target_id }}
              <span class="diff-edge-weight">{{ er.weight_before.toFixed(2) }} → {{ er.weight_after.toFixed(2) }}</span>
            </li>
          </ul>
        </div>
        <div v-if="diff.edges_weakened.length > 0" class="diff-edge-group">
          <h4 class="diff-edge-group-title diff-weakened">
            {{ t('graphDiff.legend.weakened') }} ({{ diff.edges_weakened.length }})
          </h4>
          <ul class="diff-edge-list">
            <li v-for="ew in diff.edges_weakened" :key="ew.edge.uuid" class="diff-edge-item diff-weakened">
              {{ ew.edge.source_id }} → {{ ew.edge.target_id }}
              <span class="diff-edge-weight">{{ ew.weight_before.toFixed(2) }} → {{ ew.weight_after.toFixed(2) }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Cluster-Bereich -->
      <div class="diff-clusters">
        <div v-if="diff.clusters_removed.length > 0" class="diff-cluster-group">
          <h4 class="diff-cluster-title">{{ t('graphDiff.clustersOnlyInA') }}</h4>
          <ul class="diff-cluster-list">
            <li
              v-for="cluster in diff.clusters_removed"
              :key="cluster.cluster_id"
              class="diff-cluster-item diff-removed"
            >
              {{ cluster.label }}
              <span class="diff-cluster-size">({{ cluster.member_count }})</span>
            </li>
          </ul>
        </div>
        <div v-if="diff.clusters_new.length > 0" class="diff-cluster-group">
          <h4 class="diff-cluster-title">{{ t('graphDiff.clustersOnlyInB') }}</h4>
          <ul class="diff-cluster-list">
            <li
              v-for="cluster in diff.clusters_new"
              :key="cluster.cluster_id"
              class="diff-cluster-item diff-added"
            >
              {{ cluster.label }}
              <span class="diff-cluster-size">({{ cluster.member_count }})</span>
            </li>
          </ul>
        </div>
        <div v-if="diff.cluster_shifts.length > 0" class="diff-cluster-group">
          <h4 class="diff-cluster-title">{{ t('graphDiff.clustersChanged') }}</h4>
          <ul class="diff-cluster-list">
            <li
              v-for="shift in diff.cluster_shifts"
              :key="shift.agent_id"
              class="diff-cluster-item diff-reinforced"
            >
              Agent {{ shift.agent_id }}: {{ shift.cluster_a_label }} → {{ shift.cluster_b_label }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import GraphCanvas from './GraphCanvas.vue'
import { useGraphDiff } from '../../composables/useGraphDiff'
import type { EdgeData } from '../../contracts/graphDiffContract'

// Props
const props = withDefaults(
  defineProps<{
    graphId: string
    availableSnapshots: { id: string; label: string }[]
    defaultSnapshotA?: string
    defaultSnapshotB?: string
  }>(),
  {
    defaultSnapshotA: '',
    defaultSnapshotB: '',
  }
)

const { t } = useI18n()
const { diff, loading, error, fetchDiff } = useGraphDiff()

const selectedA = ref(props.defaultSnapshotA ?? '')
const selectedB = ref(props.defaultSnapshotB ?? '')

const isSameSnapshot = computed(
  () =>
    selectedA.value !== '' &&
    selectedB.value !== '' &&
    selectedA.value === selectedB.value
)

watch(
  [selectedA, selectedB],
  ([a, b]) => {
    if (a && b && a !== b) {
      void fetchDiff(props.graphId, a, b)
    }
  },
  { immediate: true }
)

// Snapshot-Daten für GraphCanvas aufbereiten
const snapshotAGraphData = computed(() => {
  if (!diff.value) return null
  return {
    graph_id: diff.value.snapshot_a.graph_id,
    nodes: [] as unknown[],
    edges: diff.value.snapshot_a.edges.map((e: EdgeData) => ({
      ...e,
      _diffClass: edgeIdToDiffClass(e.uuid),
    })),
  }
})

const snapshotBGraphData = computed(() => {
  if (!diff.value) return null
  return {
    graph_id: diff.value.snapshot_b.graph_id,
    nodes: [] as unknown[],
    edges: diff.value.snapshot_b.edges.map((e: EdgeData) => ({
      ...e,
      _diffClass: edgeIdToDiffClass(e.uuid),
    })),
  }
})

// Diff-Klassen-Lookup: UUID → CSS-Klasse
function edgeIdToDiffClass(uuid: string): string {
  if (!diff.value) return ''
  if (diff.value.edges_added.some((e) => e.uuid === uuid)) return 'diff-added'
  if (diff.value.edges_removed.some((e) => e.uuid === uuid)) return 'diff-removed'
  if (diff.value.edges_reinforced.some((er) => er.edge.uuid === uuid)) return 'diff-reinforced'
  if (diff.value.edges_weakened.some((ew) => ew.edge.uuid === uuid)) return 'diff-weakened'
  return ''
}

// Metriken-Deltas
const nodeDelta = computed(() => {
  if (!diff.value) return 0
  return diff.value.snapshot_b.node_count - diff.value.snapshot_a.node_count
})

const edgeDelta = computed(() => {
  if (!diff.value) return 0
  return (
    diff.value.metrics.total_edges_added - diff.value.metrics.total_edges_removed
  )
})

const clusterDelta = computed(() => {
  if (!diff.value) return 0
  return diff.value.metrics.clusters_new - diff.value.metrics.clusters_removed
})

function formatDelta(n: number): string {
  if (n > 0) return `+${n}`
  return String(n)
}

function formatDeltaFloat(n: number): string {
  const formatted = n.toFixed(3)
  if (n > 0) return `+${formatted}`
  return formatted
}

function deltaClass(n: number): string {
  if (n > 0) return 'delta-positive'
  if (n < 0) return 'delta-negative'
  return 'delta-neutral'
}
</script>

<style scoped>
.diff-panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-4, 16px);
  width: 100%;
  height: 100%;
  overflow: auto;
  padding: var(--s-4, 16px);
  box-sizing: border-box;
}

/* Toolbar */
.diff-toolbar {
  display: flex;
  align-items: center;
  gap: var(--s-5, 20px);
  flex-wrap: wrap;
  padding: var(--s-3, 12px) var(--s-4, 16px);
  background: var(--bg, #fff);
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
}

.diff-selectors {
  display: flex;
  align-items: center;
  gap: var(--s-3, 12px);
}

.diff-selector-label {
  display: flex;
  flex-direction: column;
  gap: var(--s-1, 4px);
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
}

.diff-select {
  padding: 4px 8px;
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-sm, 4px);
  background: var(--bg, #fff);
  color: var(--fg, #111);
  font-size: 13px;
  cursor: pointer;
}

.diff-arrow {
  font-size: 16px;
  color: var(--fg-muted, #6b7280);
  margin-top: 16px;
}

/* Statistik-Strip */
.diff-stats {
  display: flex;
  gap: var(--s-4, 16px);
  margin-left: auto;
  flex-wrap: wrap;
}

.diff-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.diff-stat-label {
  font-family: var(--ff-mono, monospace);
  font-size: 10px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
}

.diff-stat-value {
  font-family: var(--ff-mono, monospace);
  font-size: 14px;
  font-weight: 600;
}

.delta-positive {
  color: var(--green-600, #16a34a);
}

.delta-negative {
  color: var(--red-600, #dc2626);
}

.delta-neutral {
  color: var(--fg-muted, #6b7280);
}

/* States */
.diff-empty,
.diff-loading,
.diff-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  text-align: center;
  font-family: var(--ff-mono, monospace);
  font-size: 13px;
  color: var(--fg-muted, #6b7280);
  border: 1px dashed var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
  padding: var(--s-6, 24px);
}

.diff-error {
  color: var(--red-600, #dc2626);
  border-color: var(--red-300, #fca5a5);
  background: var(--red-50, #fef2f2);
}

.diff-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--rule, #e5e7eb);
  border-top-color: var(--accent, #6366f1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: var(--s-3, 12px);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Body */
.diff-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-5, 20px);
}

/* Legende */
.diff-legend {
  display: flex;
  gap: var(--s-3, 12px);
  flex-wrap: wrap;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1, 4px);
  padding: 4px 10px;
  border-radius: var(--r-pill, 999px);
  font-size: 12px;
  font-family: var(--ff-mono, monospace);
  font-weight: 500;
}

/* Diff-Farbklassen */
.diff-added {
  color: #15803d;
  background: #dcfce7;
  border: 1px solid #86efac;
}

.diff-removed {
  color: #b91c1c;
  background: #fee2e2;
  border: 1px solid #fca5a5;
}

.diff-reinforced {
  color: #1d4ed8;
  background: #dbeafe;
  border: 1px solid #93c5fd;
}

.diff-weakened {
  color: #c2410c;
  background: #ffedd5;
  border: 1px solid #fdba74;
}

/* Zweispaltige Graph-Ansicht */
.diff-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-4, 16px);
}

.diff-column {
  display: flex;
  flex-direction: column;
  gap: var(--s-2, 8px);
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
  overflow: hidden;
}

.diff-column-header {
  padding: var(--s-2, 8px) var(--s-3, 12px);
  background: var(--bg-inverse, #f9fafb);
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
  border-bottom: 1px solid var(--rule, #e5e7eb);
}

.diff-canvas-wrap {
  height: 320px;
  position: relative;
}

/* Edge-Zusammenfassung */
.diff-edge-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--s-4, 16px);
}

.diff-edge-group {
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
  padding: var(--s-3, 12px);
}

.diff-edge-group-title {
  font-size: 12px;
  font-weight: 600;
  margin: 0 0 var(--s-2, 8px);
  padding: 4px 8px;
  border-radius: var(--r-sm, 4px);
  display: inline-block;
}

.diff-edge-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 180px;
  overflow-y: auto;
}

.diff-edge-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-radius: var(--r-sm, 4px);
  font-size: 12px;
  font-family: var(--ff-mono, monospace);
}

.diff-edge-type,
.diff-edge-weight {
  font-size: 11px;
  opacity: 0.7;
}

/* Cluster-Bereich */
.diff-clusters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--s-4, 16px);
}

.diff-cluster-group {
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
  padding: var(--s-3, 12px);
}

.diff-cluster-title {
  font-size: 12px;
  font-weight: 600;
  font-family: var(--ff-mono, monospace);
  text-transform: uppercase;
  letter-spacing: var(--ls-mono, 0.04em);
  color: var(--fg-muted, #6b7280);
  margin: 0 0 var(--s-2, 8px);
}

.diff-cluster-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diff-cluster-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-radius: var(--r-sm, 4px);
  font-size: 12px;
}

.diff-cluster-size {
  font-size: 11px;
  opacity: 0.7;
}

/* Design v3 diff panel polish. */
.diff-cluster-group {
  background: var(--surface-elevated, transparent);
  border-color: var(--hairline, var(--rule, #e5e7eb));
  border-radius: var(--r-6, var(--r-md, 8px));
}
.diff-cluster-title,
.diff-cluster-item {
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
.diff-cluster-title {
  color: var(--text-secondary, var(--fg-muted, #6b7280));
}
.diff-cluster-item {
  color: var(--text-primary, var(--fg));
}
</style>
