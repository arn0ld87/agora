<script setup lang="ts">
/**
 * Fehlerband der Bearbeitung (#1808).
 *
 * Der Client wirft typisierte Fehler: 409 `graph_locked`, 409 Konflikt, 409
 * Migration, 503 Einbettung, dazu Eingabefehler vor dem Senden und der Rest.
 * `useGraphEdit` liefert sie als `kind`; hier wird daraus je Art ein eigener
 * Text plus der Text des Backends. 409 und 503 duerfen nicht gleich aussehen —
 * 503 heisst „nichts geschrieben, spaeter erneut“, 409 „kollidiert“.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { GraphEditTestId } from '@/contracts/testIds'
import type { GraphEditErrorKind, GraphEditFailure } from '@/composables/graph-library/useGraphEdit'

const props = defineProps<{ failure: GraphEditFailure | null }>()

const emit = defineEmits<{ dismiss: [] }>()

const { t } = useI18n()

const KIND_TESTID: Record<GraphEditErrorKind, string> = {
  locked: GraphEditTestId.errorLocked,
  conflict: GraphEditTestId.errorConflict,
  migration_running: GraphEditTestId.errorMigrationRunning,
  embedding_failed: GraphEditTestId.errorEmbeddingFailed,
  invalid_input: GraphEditTestId.errorInvalidInput,
  other: GraphEditTestId.errorOther,
}

const KIND_KEY: Record<GraphEditErrorKind, string> = {
  locked: 'locked',
  conflict: 'conflict',
  migration_running: 'migrationRunning',
  embedding_failed: 'embeddingFailed',
  invalid_input: 'invalidInput',
  other: 'other',
}

const testId = computed(() => (props.failure ? KIND_TESTID[props.failure.kind] : null))
const headline = computed(() =>
  props.failure ? t(`views.graphEdit.errors.${KIND_KEY[props.failure.kind]}`) : '',
)
</script>

<template>
  <div v-if="failure" class="gee" :data-testid="GraphEditTestId.error" role="group" :aria-label="headline">
    <p class="gee__line" :data-testid="testId" role="alert">
      <span class="gee__mark" aria-hidden="true">⚠</span>
      <span class="gee__text">{{ headline }}</span>
      <span v-if="failure.message" class="gee__msg">{{ failure.message }}</span>
    </p>
    <p v-if="failure.kind === 'locked' && failure.usedBy.length" class="gee__line gee__line--quiet">
      <span class="gee__text">
        {{ t('views.graphEdit.lock.usedBy') }}:
        {{ failure.usedBy.map((user) => t('views.graphEdit.lock.simulation', { id: user.simulation_id })).join(', ') }}
      </span>
    </p>
    <button type="button" class="gee__close" @click="emit('dismiss')">
      {{ t('views.graphEdit.view.dismissError') }}
    </button>
  </div>
</template>

<style scoped>
.gee {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  padding: 10px 14px;
  border-radius: var(--ag-r-12);
  background: var(--err-soft);
  color: var(--err);
  font-size: 13px;
}

.gee__line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  margin: 0;
  flex: 1;
  min-width: 0;
}

.gee__line--quiet {
  color: var(--fg2);
  font-size: 12.5px;
}

.gee__text {
  color: var(--err);
  font-weight: 600;
}

.gee__line--quiet .gee__text {
  color: var(--fg2);
  font-weight: 400;
}

.gee__msg {
  color: var(--fg);
  font-family: var(--ag-font-mono);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.gee__close {
  border: none;
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 12.5px;
  text-decoration: underline;
  cursor: pointer;
}

.gee__close:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
