<script setup lang="ts">
/**
 * Lauf → Graph (#1797, Etappe 2, Ticket „Graph lesend“): loest das Projekt des
 * Laufs auf (`simulation_id → project_id`) und zeigt den GraphReader. Waehrend
 * des Aufbaus steht der Fortschritt an derselben Stelle. `?entity=`/`?edge=`
 * waehlen und zentrieren das Ziel (Spruenge aus dem Bericht, Etappe 5).
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import GraphProjectReader from '@/components/graph-library/GraphProjectReader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { crumbForId, useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useRunGraph } from '@/composables/graph-library/useRunGraph'
import type { ProjectGraphState } from '@/composables/graph-library/useProjectGraph'

const { t } = useI18n()
const route = useRoute()
const simulationId = computed(() => String(route.params['simulationId'] ?? ''))

const { resolution, projectId, state, project, graphData, model, reload } = useRunGraph(simulationId)

/** Erst die Aufloesung des Laufs, dann der Zustand des Graphen. */
const effectiveState = computed<ProjectGraphState>(() => {
  if (resolution.value.kind === 'loading') return { kind: 'loading' }
  if (resolution.value.kind === 'error') return { kind: 'error', message: resolution.value.message }
  return state.value
})

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.runs.title'), path: '/library/runs' },
  crumbForId(simulationId.value, `/simulations/${simulationId.value}`),
  { label: t('views.run.graph.title') },
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <div class="rgv">
    <PageHeader :title="t('views.graphLibrary.run.title')" :subtitle="project?.name || undefined">
      <template v-if="projectId && project" #right>
        <RouterLink
          class="rgv__btn"
          :to="{ name: 'GraphLibraryDetail', params: { projectId } }"
          data-testid="open-in-library"
        >
          {{ t('views.graphLibrary.run.openInLibrary') }}
        </RouterLink>
      </template>
    </PageHeader>

    <GraphProjectReader
      :state="effectiveState"
      :project-id="projectId"
      :project="project"
      :model="model"
      :graph-data="graphData"
      @retry="reload"
    />
  </div>
</template>

<style scoped>
.rgv {
  min-width: 0;
}

.rgv__btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
}

.rgv__btn:hover {
  background: var(--s4);
}

.rgv__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
