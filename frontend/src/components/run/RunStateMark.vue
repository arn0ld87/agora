<script setup lang="ts">
/**
 * Zustandsmarke (Bauplan 4.1/4.2): Text und Symbol tragen den Zustand, die
 * Farbe nur zusätzlich. "Unvollständig" (◐) und "fertig" (✓) unterscheiden
 * sich in Symbol, Text und Farbe.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { StageStateKind } from '@/composables/run/runStageState'

const props = defineProps<{ state: StageStateKind }>()
const { t } = useI18n()

const GLYPH: Record<StageStateKind, string> = {
  notStarted: '○',
  queued: '○',
  running: '',
  paused: '❚❚',
  done: '✓',
  degraded: '!',
  fallback: '↺',
  incomplete: '◐',
  stopped: '■',
  budget: '€',
  failed: '✕',
  notRecorded: '—',
}

const glyph = computed(() => GLYPH[props.state])
</script>

<template>
  <span class="run-mark" :class="`run-mark--${state}`" data-testid="run-state-mark" :data-state="state">
    <span v-if="state === 'running'" class="run-mark__spin" aria-hidden="true" />
    <span v-else class="run-mark__glyph" aria-hidden="true">{{ glyph }}</span>
    {{ t(`views.run.state.${state}`) }}
  </span>
</template>

<style scoped>
.run-mark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px 0 8px;
  border-radius: var(--ag-r-pill);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  background: var(--s3);
  color: var(--fg);
}
.run-mark__glyph {
  font-size: 10.5px;
  line-height: 1;
}
.run-mark__spin {
  width: 10px;
  height: 10px;
  box-sizing: border-box;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  animation: run-mark-spin 0.9s linear infinite;
}
@media (prefers-reduced-motion: reduce) {
  .run-mark__spin {
    animation: none;
    border-right-color: currentColor;
  }
}
@keyframes run-mark-spin {
  to {
    transform: rotate(360deg);
  }
}
.run-mark--done {
  background: var(--ok-soft);
  color: var(--ok);
}
.run-mark--degraded,
.run-mark--fallback,
.run-mark--incomplete,
.run-mark--budget {
  background: var(--warn-soft);
  color: var(--warn);
}
.run-mark--failed {
  background: var(--err-soft);
  color: var(--err);
}
.run-mark--stopped,
.run-mark--paused,
.run-mark--queued,
.run-mark--notStarted,
.run-mark--notRecorded {
  background: var(--s3);
  color: var(--fg2);
}
</style>
