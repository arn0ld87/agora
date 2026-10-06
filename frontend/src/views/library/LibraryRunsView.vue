<script setup lang="ts">
/**
 * Bibliothek → Läufe (Etappe 2, Ticket 2, #1797; Bauplan 4.1): Kacheln oder
 * Liste der Läufe, Band „Im Blick“, Filter (`?view=running|attention|with-report`),
 * Fassungen je Lauf und Mehrfachauswahl zum Vergleichen.
 *
 * Daten kommen aus der Ablage-Aggregation (`useShelf`); die Ableitungen sind
 * reine Funktionen in `composables/library/runState.ts`.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import RunNowBand from '@/components/library/runs/RunNowBand.vue'
import RunTile from '@/components/library/runs/RunTile.vue'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { useLibraryRuns } from '@/composables/library/useLibraryRuns'
import { RUNS_VIEWS, type RunsView } from '@/composables/library/runState'

const { t } = useI18n()
const router = useRouter()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.library.runs.title') },
])
useShellBreadcrumbs(crumbs)

const runs = useLibraryRuns()

const viewLabels: Record<RunsView, string> = {
  all: 'views.library.runs.views.all',
  running: 'views.library.runs.views.running',
  attention: 'views.library.runs.views.attention',
  'with-report': 'views.library.runs.views.withReport',
}

const filteredEmpty = computed(() => runs.loaded.value && !runs.isEmpty.value && runs.visible.value.length === 0)

function newRun(): void {
  void router.push({ name: 'NewRun' })
}

function compare(): void {
  const id = runs.compareSimulationId.value
  if (!runs.canCompare.value || !id) return
  void router.push({ name: 'Compare', params: { simulationId: id } })
}
</script>

<template>
  <PageHeader :title="t('views.library.runs.title')">
    <template #right>
      <button type="button" class="runs-btn runs-btn--primary" data-testid="runs-new" @click="newRun">
        {{ t('views.library.runs.empty.action') }}
      </button>
    </template>
  </PageHeader>

  <p v-if="runs.error.value" class="runs-note" role="alert" data-testid="runs-error">{{ runs.error.value }}</p>

  <RunNowBand v-if="runs.showBand.value" :running="runs.running.value" :attention="runs.attention.value" />

  <div v-if="!runs.isEmpty.value" class="runs-bar">
    <div class="runs-bar__group" role="group" :aria-label="t('views.library.runs.views.label')">
      <button
        v-for="v in RUNS_VIEWS"
        :key="v"
        type="button"
        class="runs-chip"
        :aria-pressed="runs.view.value === v"
        :data-view="v"
        @click="runs.setView(v)"
      >
        {{ t(viewLabels[v]) }}
        <span class="runs-chip__count">{{ runs.viewCounts.value[v] }}</span>
      </button>
    </div>
    <div class="runs-bar__group" role="group" :aria-label="t('views.library.runs.layout.label')">
      <button type="button" class="runs-chip" :aria-pressed="runs.layout.value === 'tiles'" data-layout="tiles" @click="runs.setLayout('tiles')">
        {{ t('views.library.runs.layout.tiles') }}
      </button>
      <button type="button" class="runs-chip" :aria-pressed="runs.layout.value === 'list'" data-layout="list" @click="runs.setLayout('list')">
        {{ t('views.library.runs.layout.list') }}
      </button>
    </div>
  </div>

  <div v-if="runs.selection.value.length > 0" class="runs-selection" role="status" data-testid="runs-selection">
    <span>{{ t('views.library.runs.selection.count', { n: runs.selection.value.length }) }}</span>
    <button type="button" class="runs-btn" data-testid="runs-compare" :disabled="!runs.canCompare.value || !runs.compareSimulationId.value" @click="compare">
      {{ t('views.library.runs.selection.compare') }}
    </button>
    <button type="button" class="runs-btn" @click="runs.clearSelection()">{{ t('views.library.runs.selection.clear') }}</button>
    <span v-if="!runs.canCompare.value" class="runs-selection__hint">{{ t('views.library.runs.selection.compareHint') }}</span>
    <span v-else-if="!runs.compareSimulationId.value" class="runs-selection__hint">{{ t('views.library.runs.selection.noSimulation') }}</span>
  </div>

  <section v-if="runs.isEmpty.value" class="runs-empty" data-testid="runs-empty">
    <p>{{ t('views.library.runs.empty.text') }}</p>
    <button type="button" class="runs-btn runs-btn--primary" data-testid="runs-empty-new" @click="newRun">
      {{ t('views.library.runs.empty.action') }}
    </button>
  </section>

  <p v-else-if="filteredEmpty" class="runs-note" data-testid="runs-filtered-empty">{{ t('views.library.runs.empty.filtered') }}</p>

  <ul v-else class="runs-grid" :class="`runs-grid--${runs.layout.value}`" :aria-label="t('views.library.runs.title')" data-testid="runs-list">
    <RunTile
      v-for="e in runs.visible.value"
      :key="e.lauf.id"
      :entry="e"
      :layout="runs.layout.value"
      :selected="runs.isSelected(e.lauf.id)"
      :versions-open="runs.isVersionsOpen(e.lauf.id)"
      :versions-state="runs.versions[e.lauf.id]"
      @toggle-select="runs.toggleSelect(e.lauf.id)"
      @toggle-versions="runs.toggleVersions(e)"
    />
  </ul>
</template>

<style scoped>
.runs-bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px 16px;
  margin-bottom: 16px;
}
.runs-bar__group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.runs-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: 999px;
  background: var(--s2);
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.runs-chip:hover {
  background: var(--s3);
}
.runs-chip[aria-pressed='true'] {
  background: var(--s4);
  color: var(--fg);
  font-weight: 600;
}
.runs-chip:focus-visible,
.runs-btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
.runs-chip__count {
  font-variant-numeric: tabular-nums;
  color: var(--fg2);
}
.runs-btn {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 8px;
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.runs-btn:hover:not(:disabled) {
  background: var(--s4);
}
.runs-btn:disabled {
  cursor: not-allowed;
  color: var(--fg2);
}
.runs-btn--primary {
  background: var(--acc);
  color: var(--fg);
}
.runs-btn--primary:hover:not(:disabled) {
  background: var(--acc-hover);
}
.runs-selection {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--s2);
  font-size: 13px;
  color: var(--fg);
}
.runs-selection__hint {
  color: var(--fg2);
}
.runs-note {
  margin: 0 0 16px;
  font-size: 13.5px;
  color: var(--fg2);
}
.runs-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
  max-width: 520px;
  padding: 24px;
  border-radius: 12px;
  background: var(--s1);
  color: var(--fg);
}
.runs-empty p {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}
.runs-grid {
  margin: 0;
  padding: 0;
  list-style: none;
}
.runs-grid--tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
  align-items: start;
}
.runs-grid--list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
