<script setup lang="ts">
/**
 * Bibliothek → Graphen (#1797, Etappe 2, Ticket „Graph lesend“): Kacheln aller
 * Graphen. Kennung ist die `project_id` (`/graphs/:projectId`); die Zahl der
 * Entitaeten und Beziehungen liefert die Projektliste nicht und wird daher nicht gezeigt.
 */
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useGraphLibrary } from '@/composables/graph-library/useGraphLibrary'

const { t, te, locale } = useI18n()
const { graphs, loading, error, notices, isEmpty, reload } = useGraphLibrary()

onMounted(() => void reload())

function stateText(status: string): string {
  const key = `shelf.status.project_${status}`
  return te(key) ? t(key) : status
}

function dateText(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(locale.value, { day: '2-digit', month: '2-digit', year: 'numeric' })
}

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.library.graphs.title') },
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <div class="lgv">
    <PageHeader :title="t('views.library.graphs.title')">
      <template v-if="!loading && !error" #right>
        <span class="lgv__count" data-testid="graph-count">{{ graphs.length }}</span>
      </template>
    </PageHeader>

    <p v-if="loading" class="lgv__text" role="status" aria-busy="true">{{ t('views.graphLibrary.library.loading') }}</p>

    <div v-else-if="error" class="lgv__err" role="alert" data-testid="library-error">
      <p class="lgv__errtitle">{{ t('views.graphLibrary.library.errorTitle') }}</p>
      <p class="lgv__text lgv__text--fg">{{ error }}</p>
      <button type="button" class="lgv__btn" @click="reload">{{ t('views.graphLibrary.state.retry') }}</button>
    </div>

    <template v-else>
      <p v-for="note in notices" :key="note" class="lgv__notice" role="status">{{ note }}</p>

      <p v-if="isEmpty" class="lgv__empty" data-testid="library-empty">
        {{ t('views.graphLibrary.library.empty') }}
      </p>

      <ul v-else class="lgv__grid" :aria-label="t('views.library.graphs.title')">
        <li v-for="graph in graphs" :key="graph.projectId">
          <RouterLink
            class="lgv__tile"
            :to="{ name: 'GraphLibraryDetail', params: { projectId: graph.projectId } }"
            :data-project-id="graph.projectId"
          >
            <span class="lgv__top">
              <span class="lgv__chip">{{ stateText(graph.status) }}</span>
              <span class="lgv__date">{{ dateText(graph.updatedAt) }}</span>
            </span>
            <span class="lgv__name">{{ graph.name }}</span>
            <span v-if="graph.source" class="lgv__src">
              {{ graph.source }}<template v-if="graph.extraSources > 0"> {{ t('views.graphLibrary.library.moreSources', { n: graph.extraSources }) }}</template>
            </span>
            <span class="lgv__runs">
              {{
                graph.runCount === null
                  ? t('views.graphLibrary.library.runsUnknown')
                  : graph.runCount === 1
                    ? t('views.graphLibrary.library.runsOne')
                    : t('views.graphLibrary.library.runs', { n: graph.runCount })
              }}
            </span>
          </RouterLink>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.lgv {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.lgv__count {
  color: var(--fg2);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.lgv__text {
  margin: 0;
  color: var(--fg2);
  font-size: 13.5px;
}

.lgv__text--fg {
  color: var(--fg);
}

.lgv__err {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  max-width: 640px;
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--err-soft);
}

.lgv__errtitle {
  margin: 0;
  color: var(--err);
  font-size: 15px;
  font-weight: 650;
}

.lgv__btn {
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.lgv__btn:hover {
  background: var(--s4);
}

.lgv__notice {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 13px;
}

.lgv__empty {
  margin: 0;
  max-width: 560px;
  padding: 24px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg2);
  font-size: 14px;
  line-height: 1.5;
}

.lgv__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.lgv__tile {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-width: 0;
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
  text-decoration: none;
}

.lgv__tile:hover {
  background: var(--s3);
}

.lgv__tile:focus-visible,
.lgv__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.lgv__top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lgv__chip {
  padding: 2px 10px;
  border-radius: var(--ag-r-pill);
  background: var(--s3);
  color: var(--fg2);
  font-size: 12px;
  font-weight: 600;
}

.lgv__date {
  margin-left: auto;
  color: var(--fg3);
  font-size: 12.5px;
}

.lgv__name {
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.lgv__src {
  color: var(--fg3);
  font-family: var(--ag-font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.lgv__runs {
  margin-top: auto;
  color: var(--fg2);
  font-size: 13px;
}
</style>
