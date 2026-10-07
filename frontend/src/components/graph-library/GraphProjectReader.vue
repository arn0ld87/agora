<script setup lang="ts">
/**
 * Zustandshuelle um den GraphReader (#1797): Laden, Fehler, „kein Graph“,
 * Aufbau mit Fortschritt (bei vorliegendem Teilgraph samt Leser) und fertig.
 * Gemeinsam fuer Lauf-Graph und Bibliotheks-Detail.
 *
 * `editable` (#1808, Entscheid 9) tauscht den Leser gegen die bearbeitbare
 * Ansicht: im Lauf bleibt es beim Leser, in der Bibliothek wird bearbeitet.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Project } from '@/contracts/projectContract'
import type { GraphData, ReaderModel } from '@/composables/graph-library/graphReaderModel'
import type { ProjectGraphState } from '@/composables/graph-library/useProjectGraph'
import GraphEditView from '@/components/graph-edit/GraphEditView.vue'
import GraphReader from './GraphReader.vue'

const props = withDefaults(
  defineProps<{
    state: ProjectGraphState
    projectId: string | null
    project: Project | null
    model: ReaderModel | null
    graphData: GraphData | null
    editable?: boolean
  }>(),
  { editable: false },
)

const emit = defineEmits<{ retry: []; changed: [] }>()

const { t } = useI18n()

const notice = computed(() =>
  props.state.kind === 'ready' && props.state.incomplete ? t('views.graphLibrary.state.incomplete') : null,
)
const percent = computed(() => (props.state.kind === 'building' ? props.state.progress : null))
</script>

<template>
  <div class="gpr">
    <p v-if="state.kind === 'loading' || state.kind === 'idle'" class="gpr__state" role="status" aria-busy="true">
      {{ t('views.graphLibrary.state.loading') }}
    </p>

    <div v-else-if="state.kind === 'error'" class="gpr__state gpr__state--err" role="alert">
      <p class="gpr__title">{{ t('views.graphLibrary.state.errorTitle') }}</p>
      <p class="gpr__text">{{ state.message }}</p>
      <button type="button" class="gpr__btn" @click="$emit('retry')">{{ t('views.graphLibrary.state.retry') }}</button>
    </div>

    <div v-else-if="state.kind === 'no-graph'" class="gpr__state" role="status" data-testid="gpr-no-graph">
      <p class="gpr__title">{{ t('views.graphLibrary.state.noGraphTitle') }}</p>
      <p class="gpr__text">
        {{ state.reason === 'failed' ? t('views.graphLibrary.state.failed') : t('views.graphLibrary.state.notBuilt') }}
      </p>
      <p v-if="state.reason === 'failed' && project?.error" class="gpr__text gpr__text--mono">{{ project.error }}</p>
      <RouterLink
        v-if="projectId"
        class="gpr__btn gpr__btn--link"
        :to="{ name: 'StepGraphBuild', params: { projectId } }"
      >
        {{ t('views.graphLibrary.state.openBuild') }}
      </RouterLink>
    </div>

    <template v-else>
      <div v-if="state.kind === 'building'" class="gpr__state" role="status" data-testid="gpr-building">
        <p class="gpr__title">{{ t('views.graphLibrary.state.buildingTitle') }}</p>
        <progress
          v-if="percent !== null"
          class="gpr__bar"
          max="100"
          :value="percent"
          :aria-label="t('views.graphLibrary.state.buildingTitle')"
        />
        <p class="gpr__text">
          {{ percent !== null ? `${percent} %` : t('views.graphLibrary.state.buildingNoProgress') }}
          <template v-if="state.message"> · {{ state.message }}</template>
        </p>
        <RouterLink
          v-if="projectId"
          class="gpr__btn gpr__btn--link"
          :to="{ name: 'StepGraphBuild', params: { projectId } }"
        >
          {{ t('views.graphLibrary.state.openBuild') }}
        </RouterLink>
      </div>

      <!-- Der Server bleibt die Quelle der Wahrheit: nach jeder Aktion neu laden. -->
      <GraphEditView
        v-if="editable && model && graphData"
        :model="model"
        :graph-data="graphData"
        :notice="notice"
        :graph-name="project?.name ?? null"
        @changed="emit('changed')"
      />
      <GraphReader v-else-if="model && graphData" :model="model" :graph-data="graphData" :notice="notice">
        <template #actions><slot name="actions" /></template>
      </GraphReader>
      <slot v-else-if="state.kind === 'ready'" name="empty" />
    </template>
  </div>
</template>

<style scoped>
.gpr {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.gpr__state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  max-width: 640px;
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}

.gpr__state--err {
  background: var(--err-soft);
}

.gpr__title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}

.gpr__state--err .gpr__title {
  color: var(--err);
}

.gpr__text {
  margin: 0;
  color: var(--fg2);
  font-size: 13.5px;
  line-height: 1.5;
}

.gpr__state--err .gpr__text {
  color: var(--fg);
}

.gpr__text--mono {
  font-family: var(--ag-font-mono);
  font-size: 12.5px;
  overflow-wrap: anywhere;
}

.gpr__bar {
  width: 100%;
  height: 8px;
  accent-color: var(--acc);
}

.gpr__btn {
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
  cursor: pointer;
  text-decoration: none;
}

.gpr__btn:hover {
  background: var(--s4);
}

.gpr__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
