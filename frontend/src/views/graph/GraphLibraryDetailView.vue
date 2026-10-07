<script setup lang="ts">
/**
 * Graphen-Bibliothek → Graph (#1797, Etappe 2, Ticket „Graph lesend“): GraphReader
 * plus die Laeufe, die auf diesem Graphen laufen. „Neuer Lauf auf diesem Graphen“
 * fuehrt in die bestehende Build-Ansicht (Route `StepGraphBuild`): ihr „Weiter“
 * legt per `POST /api/simulation/create` einen NEUEN Lauf auf dem fertigen
 * Projekt an (`Step1GraphBuild::enterEnvSetup`), baut den Graphen nicht neu.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import GraphProjectReader from '@/components/graph-library/GraphProjectReader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { crumbForId, useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useProjectGraph } from '@/composables/graph-library/useProjectGraph'
import { useGraphRuns } from '@/composables/graph-library/useGraphLibrary'

const { t, te } = useI18n()
const route = useRoute()
const projectId = computed(() => String(route.params['projectId'] ?? ''))
const projectIdRef = ref<string | null>(projectId.value || null)
watch(projectId, (id) => (projectIdRef.value = id || null))

const { state, project, graphData, model, reload } = useProjectGraph(projectIdRef)
const { runs, loading: runsLoading, error: runsError, load: loadRuns } = useGraphRuns()

onMounted(() => void loadRuns(projectId.value))
watch(projectId, (id) => void loadRuns(id))

/** Nur ein vollstaendig gebauter Graph taugt als Grundlage fuer einen weiteren Lauf. */
const canStartRun = computed(
  () => state.value.kind === 'ready' && !state.value.incomplete && project.value?.status === 'graph_completed',
)

const subtitle = computed(() => {
  const p = project.value
  if (!p) return undefined
  const first = p.files.map((f) => f['filename']).find((n): n is string => typeof n === 'string' && n.length > 0)
  const status = te(`shelf.status.project_${p.status}`) ? t(`shelf.status.project_${p.status}`) : p.status
  return first ? `${first} · ${status}` : status
})

function runStatus(status: string): string {
  const key = `views.graphLibrary.runStatus.${status}`
  return te(key) ? t(key) : status
}

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.graphs.title'), path: '/library/graphs' },
  crumbForId(projectId.value),
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <div class="gld">
    <PageHeader :title="project?.name || t('views.graphLibrary.title')" :subtitle="subtitle">
      <template #right>
        <RouterLink
          v-if="canStartRun"
          class="gld__btn gld__btn--primary"
          :to="{ name: 'StepGraphBuild', params: { projectId } }"
          data-testid="new-run"
        >
          {{ t('views.graphLibrary.detail.newRun') }}
        </RouterLink>
        <button
          v-else
          type="button"
          class="gld__btn"
          disabled
          aria-disabled="true"
          :title="t('views.graphLibrary.detail.newRunUnavailable')"
          data-testid="new-run-disabled"
        >
          {{ t('views.graphLibrary.detail.newRun') }}
        </button>
      </template>
    </PageHeader>

    <GraphProjectReader
      :state="state"
      :project-id="projectId"
      :project="project"
      :model="model"
      :graph-data="graphData"
      @retry="reload"
    />

    <section class="gld__runs" :aria-label="t('views.graphLibrary.detail.runsTitle')">
      <h2 class="gld__h">
        {{ t('views.graphLibrary.detail.runsTitle') }}
        <span v-if="!runsLoading && !runsError" class="gld__n">{{ runs.length }}</span>
      </h2>
      <p v-if="runsLoading" class="gld__text" role="status">{{ t('views.graphLibrary.detail.runsLoading') }}</p>
      <p v-else-if="runsError" class="gld__text gld__text--err" role="alert" data-testid="runs-error">
        {{ runsError }}
      </p>
      <p v-if="!runsLoading && !runsError && runs.length === 0" class="gld__text" data-testid="runs-empty">
        {{ t('views.graphLibrary.detail.runsEmpty') }}
      </p>
      <ul v-if="!runsLoading && runs.length > 0" class="gld__list">
        <li v-for="run in runs" :key="run.simulation_id">
          <RouterLink
            class="gld__run"
            :to="{ name: 'RunOverview', params: { simulationId: run.simulation_id } }"
          >
            <span class="gld__id">{{ run.simulation_id }}</span>
            <span class="gld__status">{{ runStatus(run.status) }}</span>
            <span class="gld__date">{{ run.created_at ?? run.updated_at ?? '' }}</span>
          </RouterLink>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.gld {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.gld__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
}

.gld__btn:disabled {
  color: var(--fg2);
  cursor: not-allowed;
}

.gld__btn--primary {
  background: var(--acc);
  color: var(--on-acc);
}

.gld__btn--primary:hover {
  background: var(--acc-hover);
}

.gld__btn:focus-visible,
.gld__run:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.gld__runs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gld__h {
  display: flex;
  gap: 8px;
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  color: var(--fg);
}

.gld__n {
  color: var(--fg2);
  font-weight: 400;
  font-variant-numeric: tabular-nums;
}

.gld__text {
  margin: 0;
  color: var(--fg2);
  font-size: 13.5px;
}

.gld__text--err {
  color: var(--err);
}

.gld__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.gld__run {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font-size: 13.5px;
  text-decoration: none;
}

.gld__run:hover {
  background: var(--s3);
}

.gld__id {
  font-family: var(--ag-font-mono);
  overflow-wrap: anywhere;
}

.gld__status,
.gld__date {
  color: var(--fg2);
}
</style>
