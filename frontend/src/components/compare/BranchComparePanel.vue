<template>
  <div class="compare-panel">
    <!-- Top-Bar mit Branch-Selektoren -->
    <header class="compare-toolbar">
      <div class="compare-selectors">
        <span class="compare-sim-label">
          <span class="compare-label-text">{{ t('branchCompare.simulationLabel') }}</span>
          <span class="compare-sim-id">{{ simulationId }}</span>
        </span>
        <label class="compare-selector-label">
          {{ t('branchCompare.branchA') }}
          <select v-model="selectedA" class="compare-select">
            <option value="" disabled>—</option>
            <option
              v-for="branch in availableBranches"
              :key="branch.id"
              :value="branch.id"
            >
              {{ branch.label }}
            </option>
          </select>
        </label>
        <span class="compare-arrow">→</span>
        <label class="compare-selector-label">
          {{ t('branchCompare.branchB') }}
          <select v-model="selectedB" class="compare-select">
            <option value="" disabled>—</option>
            <option
              v-for="branch in availableBranches"
              :key="branch.id"
              :value="branch.id"
            >
              {{ branch.label }}
            </option>
          </select>
        </label>
      </div>
    </header>

    <!-- Empty-State: keine Branches gewählt -->
    <div v-if="!selectedA || !selectedB" class="compare-empty">
      <p>{{ t('branchCompare.empty.selectBranches') }}</p>
    </div>

    <!-- Empty-State: gleiche Branches gewählt -->
    <div v-else-if="isSameBranch" class="compare-empty">
      <p>{{ t('branchCompare.empty.sameBranches') }}</p>
    </div>

    <!-- Loading-State -->
    <div v-else-if="loading" class="compare-loading">
      <div class="compare-spinner"></div>
      <p>{{ t('branchCompare.loading') }}</p>
    </div>

    <!-- Error-State -->
    <div v-else-if="error" class="compare-error" role="alert">
      <p>{{ t('branchCompare.error.generic') }}: {{ error }}</p>
    </div>

    <!-- Hauptinhalt: Vergleich -->
    <div v-else-if="comparison" class="compare-body">
      <!-- Statistik-Strip (Δ-Block) -->
      <div class="compare-delta-strip">
        <div class="delta-tile">
          <span class="delta-tile-label">{{ t('branchCompare.deltas.echoChamber') }}</span>
          <span
            class="delta-tile-value"
            :class="deltaClass(comparison.deltas.echo_chamber_delta)"
          >{{ formatDeltaFloat(comparison.deltas.echo_chamber_delta) }}</span>
        </div>
        <div class="delta-tile">
          <span class="delta-tile-label">{{ t('branchCompare.deltas.clusters') }}</span>
          <span
            class="delta-tile-value"
            :class="deltaClass(comparison.deltas.cluster_delta)"
          >{{ formatDeltaInt(comparison.deltas.cluster_delta) }}</span>
        </div>
        <div class="delta-tile">
          <span class="delta-tile-label">{{ t('branchCompare.deltas.bridgeAgents') }}</span>
          <span
            class="delta-tile-value"
            :class="deltaClass(comparison.deltas.bridge_agents_delta)"
          >{{ formatDeltaInt(comparison.deltas.bridge_agents_delta) }}</span>
        </div>
        <div class="delta-tile">
          <span class="delta-tile-label">{{ t('branchCompare.deltas.avgEvidence') }}</span>
          <span
            class="delta-tile-value"
            :class="deltaClass(comparison.deltas.avg_evidence_delta)"
          >{{ formatDeltaFloat(comparison.deltas.avg_evidence_delta) }}</span>
        </div>
        <div class="delta-tile">
          <span class="delta-tile-label">{{ t('branchCompare.deltas.contradictionRatio') }}</span>
          <span
            class="delta-tile-value"
            :class="deltaClass(comparison.deltas.contradiction_ratio_delta)"
          >{{ formatDeltaFloat(comparison.deltas.contradiction_ratio_delta) }}</span>
        </div>
        <div class="delta-tile">
          <span class="delta-tile-label">{{ t('branchCompare.deltas.interactionDensity') }}</span>
          <span
            class="delta-tile-value"
            :class="deltaClass(comparison.deltas.interaction_density_delta)"
          >{{ formatDeltaFloat(comparison.deltas.interaction_density_delta) }}</span>
        </div>
      </div>

      <!-- Branch-Karten (zweispaltig) -->
      <div class="compare-columns">
        <!-- Branch A -->
        <div class="branch-card">
          <div class="branch-card-header">
            <span class="branch-card-id">{{ comparison.branch_a_id }}</span>
            <span class="branch-card-completed">
              {{ t('branchCompare.completedAt') }}:
              {{ formatDate(comparison.branch_a_completed_at) }}
            </span>
          </div>
          <div class="branch-kpi-block">
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.echoChamberIndex') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.echo_chamber_index.toFixed(3) }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.clusterCount') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.cluster_count }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.bridgeAgents') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.bridge_agent_ids.length }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.totalAgents') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.total_agents }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.totalInteractions') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.total_interactions }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.interactionDensity') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.interaction_density.toFixed(2) }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.avgEvidencePerClaim') }}</span>
              <span class="kpi-value">{{ comparison.metrics_a.avg_evidence_per_claim.toFixed(2) }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.claimsWithoutEvidenceRatio') }}</span>
              <span class="kpi-value">{{ (comparison.metrics_a.claims_without_evidence_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.contradictionRatio') }}</span>
              <span class="kpi-value">{{ (comparison.metrics_a.contradiction_ratio * 100).toFixed(1) }}%</span>
            </div>
          </div>
          <!-- Confidence-Distribution -->
          <div class="branch-confidence">
            <div class="branch-section-title">{{ t('branchCompare.metrics.confidenceDistribution') }}</div>
            <div class="confidence-bars">
              <div
                v-for="key in confidenceKeys"
                :key="key"
                class="confidence-bar-row"
              >
                <span class="confidence-bar-label">{{ t(`branchCompare.confidence.${key}`) }}</span>
                <span class="confidence-bar-count">{{ comparison.metrics_a.confidence_distribution[key] }}</span>
              </div>
            </div>
          </div>
          <!-- Persona-Reach -->
          <div class="branch-persona-reach">
            <div class="branch-section-title">{{ t('branchCompare.metrics.personaReach') }}</div>
            <ul class="persona-reach-list">
              <li
                v-for="(reach, segName) in comparison.metrics_a.persona_reach"
                :key="segName"
                class="persona-reach-item"
              >
                <span class="persona-reach-segment">{{ segName }}</span>
                <span class="persona-reach-counts">{{ reach.active_count }} / {{ reach.total_count }}</span>
                <span class="persona-reach-ratio">{{ (reach.ratio * 100).toFixed(1) }}%</span>
              </li>
            </ul>
          </div>
          <!-- Top-3 dominant_clusters -->
          <div
            v-if="comparison.metrics_a.dominant_clusters.length > 0"
            class="branch-dominant-clusters"
          >
            <div class="branch-section-title">{{ t('branchCompare.metrics.dominantClusters') }}</div>
            <ul class="dominant-cluster-list">
              <li
                v-for="cluster in comparison.metrics_a.dominant_clusters.slice(0, 3)"
                :key="cluster.cluster_id"
                class="dominant-cluster-item"
              >
                <span class="dominant-cluster-label">{{ cluster.label }}</span>
                <span class="dominant-cluster-size">({{ cluster.size }})</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- Branch B -->
        <div class="branch-card">
          <div class="branch-card-header">
            <span class="branch-card-id">{{ comparison.branch_b_id }}</span>
            <span class="branch-card-completed">
              {{ t('branchCompare.completedAt') }}:
              {{ formatDate(comparison.branch_b_completed_at) }}
            </span>
          </div>
          <div class="branch-kpi-block">
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.echoChamberIndex') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.echo_chamber_index.toFixed(3) }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.clusterCount') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.cluster_count }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.bridgeAgents') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.bridge_agent_ids.length }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.totalAgents') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.total_agents }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.totalInteractions') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.total_interactions }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.interactionDensity') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.interaction_density.toFixed(2) }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.avgEvidencePerClaim') }}</span>
              <span class="kpi-value">{{ comparison.metrics_b.avg_evidence_per_claim.toFixed(2) }}</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.claimsWithoutEvidenceRatio') }}</span>
              <span class="kpi-value">{{ (comparison.metrics_b.claims_without_evidence_ratio * 100).toFixed(1) }}%</span>
            </div>
            <div class="kpi-tile">
              <span class="kpi-label">{{ t('branchCompare.metrics.contradictionRatio') }}</span>
              <span class="kpi-value">{{ (comparison.metrics_b.contradiction_ratio * 100).toFixed(1) }}%</span>
            </div>
          </div>
          <!-- Confidence-Distribution -->
          <div class="branch-confidence">
            <div class="branch-section-title">{{ t('branchCompare.metrics.confidenceDistribution') }}</div>
            <div class="confidence-bars">
              <div
                v-for="key in confidenceKeys"
                :key="key"
                class="confidence-bar-row"
              >
                <span class="confidence-bar-label">{{ t(`branchCompare.confidence.${key}`) }}</span>
                <span class="confidence-bar-count">{{ comparison.metrics_b.confidence_distribution[key] }}</span>
              </div>
            </div>
          </div>
          <!-- Persona-Reach -->
          <div class="branch-persona-reach">
            <div class="branch-section-title">{{ t('branchCompare.metrics.personaReach') }}</div>
            <ul class="persona-reach-list">
              <li
                v-for="(reach, segName) in comparison.metrics_b.persona_reach"
                :key="segName"
                class="persona-reach-item"
              >
                <span class="persona-reach-segment">{{ segName }}</span>
                <span class="persona-reach-counts">{{ reach.active_count }} / {{ reach.total_count }}</span>
                <span class="persona-reach-ratio">{{ (reach.ratio * 100).toFixed(1) }}%</span>
              </li>
            </ul>
          </div>
          <!-- Top-3 dominant_clusters -->
          <div
            v-if="comparison.metrics_b.dominant_clusters.length > 0"
            class="branch-dominant-clusters"
          >
            <div class="branch-section-title">{{ t('branchCompare.metrics.dominantClusters') }}</div>
            <ul class="dominant-cluster-list">
              <li
                v-for="cluster in comparison.metrics_b.dominant_clusters.slice(0, 3)"
                :key="cluster.cluster_id"
                class="dominant-cluster-item"
              >
                <span class="dominant-cluster-label">{{ cluster.label }}</span>
                <span class="dominant-cluster-size">({{ cluster.size }})</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Cluster-Bereich: drei Listen -->
      <div class="compare-clusters">
        <div
          v-if="comparison.deltas.clusters_only_in_a.length > 0"
          class="compare-cluster-group"
        >
          <h4 class="compare-cluster-title">
            {{ t('branchCompare.clustersOnlyInA') }}
            ({{ comparison.deltas.clusters_only_in_a.length }})
          </h4>
          <ul class="compare-cluster-list">
            <li
              v-for="cluster in comparison.deltas.clusters_only_in_a"
              :key="cluster.cluster_id"
              class="compare-cluster-item cluster-only-a"
            >
              <span class="cluster-item-id">#{{ cluster.cluster_id }}</span>
              <span class="cluster-item-label">{{ cluster.label }}</span>
              <span class="cluster-item-size">({{ cluster.size }})</span>
            </li>
          </ul>
        </div>
        <div
          v-if="comparison.deltas.clusters_only_in_b.length > 0"
          class="compare-cluster-group"
        >
          <h4 class="compare-cluster-title">
            {{ t('branchCompare.clustersOnlyInB') }}
            ({{ comparison.deltas.clusters_only_in_b.length }})
          </h4>
          <ul class="compare-cluster-list">
            <li
              v-for="cluster in comparison.deltas.clusters_only_in_b"
              :key="cluster.cluster_id"
              class="compare-cluster-item cluster-only-b"
            >
              <span class="cluster-item-id">#{{ cluster.cluster_id }}</span>
              <span class="cluster-item-label">{{ cluster.label }}</span>
              <span class="cluster-item-size">({{ cluster.size }})</span>
            </li>
          </ul>
        </div>
        <div
          v-if="comparison.deltas.clusters_changed.length > 0"
          class="compare-cluster-group"
        >
          <h4 class="compare-cluster-title">
            {{ t('branchCompare.clustersChanged') }}
            ({{ comparison.deltas.clusters_changed.length }})
          </h4>
          <ul class="compare-cluster-list">
            <li
              v-for="change in comparison.deltas.clusters_changed"
              :key="change.cluster_id"
              class="compare-cluster-item cluster-changed"
            >
              <span class="cluster-item-id">#{{ change.cluster_id }}</span>
              <span class="cluster-item-sizes">{{ change.size_a }} → {{ change.size_b }}</span>
              <span class="cluster-item-labels">{{ change.label_a }} → {{ change.label_b }}</span>
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
import { useBranchComparison } from '../../composables/useBranchComparison'

// Props
const props = withDefaults(
  defineProps<{
    simulationId: string
    availableBranches: { id: string; label: string; completed_at?: string }[]
    defaultBranchA?: string
    defaultBranchB?: string
  }>(),
  {
    defaultBranchA: '',
    defaultBranchB: '',
  }
)

const { t } = useI18n()
const { comparison, loading, error, fetchComparison } = useBranchComparison()

const selectedA = ref(props.defaultBranchA ?? '')
const selectedB = ref(props.defaultBranchB ?? '')

const isSameBranch = computed(
  () =>
    selectedA.value !== '' &&
    selectedB.value !== '' &&
    selectedA.value === selectedB.value
)

const confidenceKeys = ['low', 'medium', 'high', 'verified'] as const

watch(
  [selectedA, selectedB],
  ([a, b]) => {
    if (a && b && a !== b) {
      void fetchComparison(props.simulationId, a, b)
    }
  },
  { immediate: true }
)

function formatDeltaInt(n: number): string {
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
  return 'delta-zero'
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
</script>

<style scoped>
.compare-panel {
  display: flex;
  flex-direction: column;
  gap: var(--s-4, 16px);
  width: 100%;
  overflow: auto;
  padding: var(--s-4, 16px);
  box-sizing: border-box;
}

/* Toolbar */
.compare-toolbar {
  display: flex;
  align-items: center;
  gap: var(--s-5, 20px);
  flex-wrap: wrap;
  padding: var(--s-3, 12px) var(--s-4, 16px);
  background: var(--bg, #fff);
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
}

.compare-selectors {
  display: flex;
  align-items: center;
  gap: var(--s-3, 12px);
  flex-wrap: wrap;
}

.compare-sim-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.compare-label-text {
  font-family: var(--ff-mono, monospace);
  font-size: 10px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
}

.compare-sim-id {
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  color: var(--fg, #111);
}

.compare-selector-label {
  display: flex;
  flex-direction: column;
  gap: var(--s-1, 4px);
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
}

.compare-select {
  padding: 4px 8px;
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-sm, 4px);
  background: var(--bg, #fff);
  color: var(--fg, #111);
  font-size: 13px;
  cursor: pointer;
}

.compare-arrow {
  font-size: 16px;
  color: var(--fg-muted, #6b7280);
  margin-top: 16px;
}

/* States */
.compare-empty,
.compare-loading,
.compare-error {
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

.compare-error {
  color: var(--red-600, #dc2626);
  border-color: var(--red-300, #fca5a5);
  background: var(--red-50, #fef2f2);
}

.compare-spinner {
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
.compare-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-5, 20px);
}

/* Δ-Strip */
.compare-delta-strip {
  display: flex;
  gap: var(--s-3, 12px);
  flex-wrap: wrap;
  padding: var(--s-3, 12px) var(--s-4, 16px);
  background: var(--bg-inverse, #f9fafb);
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
}

.delta-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 80px;
}

.delta-tile-label {
  font-family: var(--ff-mono, monospace);
  font-size: 10px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
  text-align: center;
}

.delta-tile-value {
  font-family: var(--ff-mono, monospace);
  font-size: 16px;
  font-weight: 600;
}

.delta-positive {
  color: var(--color-success-fg, #1f7a1f);
}

.delta-negative {
  color: var(--red-600, #dc2626);
}

.delta-zero {
  color: var(--fg-muted, #6b7280);
}

/* Branch-Karten */
.compare-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-4, 16px);
}

@media (max-width: 768px) {
  .compare-columns {
    grid-template-columns: 1fr;
  }
}

.branch-card {
  display: flex;
  flex-direction: column;
  gap: var(--s-3, 12px);
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
  overflow: hidden;
}

.branch-card-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--s-2, 8px) var(--s-3, 12px);
  background: var(--bg-inverse, #f9fafb);
  border-bottom: 1px solid var(--rule, #e5e7eb);
}

.branch-card-id {
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  font-weight: 600;
  color: var(--fg, #111);
}

.branch-card-completed {
  font-family: var(--ff-mono, monospace);
  font-size: 10px;
  color: var(--fg-muted, #6b7280);
}

/* KPI-Block */
.branch-kpi-block {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--s-2, 8px);
  padding: var(--s-3, 12px);
}

.kpi-tile {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--s-2, 8px);
  background: var(--bg-inverse, #f9fafb);
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-sm, 4px);
}

.kpi-label {
  font-family: var(--ff-mono, monospace);
  font-size: 9px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
}

.kpi-value {
  font-family: var(--ff-mono, monospace);
  font-size: 14px;
  font-weight: 600;
  color: var(--fg, #111);
}

/* Confidence Distribution */
.branch-confidence,
.branch-persona-reach,
.branch-dominant-clusters {
  padding: 0 var(--s-3, 12px) var(--s-3, 12px);
}

.branch-section-title {
  font-family: var(--ff-mono, monospace);
  font-size: 10px;
  letter-spacing: var(--ls-mono, 0.04em);
  text-transform: uppercase;
  color: var(--fg-muted, #6b7280);
  margin-bottom: var(--s-2, 8px);
}

.confidence-bars {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.confidence-bar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
}

.confidence-bar-label {
  color: var(--fg-muted, #6b7280);
  text-transform: capitalize;
}

.confidence-bar-count {
  font-weight: 600;
  color: var(--fg, #111);
}

/* Persona Reach */
.persona-reach-list,
.dominant-cluster-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 160px;
  overflow-y: auto;
}

.persona-reach-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-2, 8px);
  padding: 2px 0;
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
}

.persona-reach-segment {
  color: var(--fg, #111);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.persona-reach-counts {
  color: var(--fg-muted, #6b7280);
  white-space: nowrap;
}

.persona-reach-ratio {
  font-weight: 600;
  color: var(--fg, #111);
  white-space: nowrap;
}

/* Dominant Clusters */
.dominant-cluster-item {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  padding: 2px 0;
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
}

.dominant-cluster-label {
  color: var(--fg, #111);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dominant-cluster-size {
  color: var(--fg-muted, #6b7280);
  white-space: nowrap;
}

/* Cluster-Bereich */
.compare-clusters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--s-4, 16px);
}

.compare-cluster-group {
  border: 1px solid var(--rule, #e5e7eb);
  border-radius: var(--r-md, 8px);
  padding: var(--s-3, 12px);
}

.compare-cluster-title {
  font-size: 12px;
  font-weight: 600;
  font-family: var(--ff-mono, monospace);
  text-transform: uppercase;
  letter-spacing: var(--ls-mono, 0.04em);
  color: var(--fg-muted, #6b7280);
  margin: 0 0 var(--s-2, 8px);
}

.compare-cluster-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.compare-cluster-item {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  padding: 4px 8px;
  border-radius: var(--r-sm, 4px);
  font-size: 12px;
  font-family: var(--ff-mono, monospace);
}

.cluster-only-a {
  background: #fee2e2;
  color: #b91c1c;
  border: 1px solid #fca5a5;
}

.cluster-only-b {
  background: #dcfce7;
  color: #15803d;
  border: 1px solid #86efac;
}

.cluster-changed {
  background: #dbeafe;
  color: #1d4ed8;
  border: 1px solid #93c5fd;
}

.cluster-item-id {
  font-size: 10px;
  opacity: 0.7;
  white-space: nowrap;
}

.cluster-item-label,
.cluster-item-labels {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cluster-item-size,
.cluster-item-sizes {
  white-space: nowrap;
  opacity: 0.8;
}
</style>
