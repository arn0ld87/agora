<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { STATE_GLYPH, type LibraryState } from '@/composables/library/runState'

/**
 * Zustandsmarke eines Laufs: Zeichen UND Wort, nie nur Farbe. „Unvollstaendig“
 * (◐, Warnflaeche) sieht nie aus wie „Fertig“ (✓, Okflaeche).
 */
const props = defineProps<{ state: LibraryState }>()
const { t } = useI18n()
const label = computed(() => t(`views.library.runs.state.${props.state}`))
const glyph = computed(() => STATE_GLYPH[props.state])
</script>

<template>
  <span class="state-mark" :class="`state-mark--${state}`" :data-state="state">
    <span v-if="state === 'running'" class="state-mark__spin" aria-hidden="true" />
    <span v-else class="state-mark__glyph" aria-hidden="true">{{ glyph }}</span>
    <span class="state-mark__label">{{ label }}</span>
  </span>
</template>

<style scoped>
.state-mark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px 0 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  background: var(--s3);
  color: var(--fg);
}
.state-mark__glyph {
  font-size: 10.5px;
  line-height: 1;
}
.state-mark__spin {
  width: 10px;
  height: 10px;
  box-sizing: border-box;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  animation: run-spin 0.9s linear infinite;
}
.state-mark--paused,
.state-mark--stopped,
.state-mark--pending,
.state-mark--unknown {
  background: var(--s3);
  color: var(--fg2);
}
.state-mark--done {
  background: var(--ok-soft);
  color: var(--ok);
}
.state-mark--incomplete,
.state-mark--budget {
  background: var(--warn-soft);
  color: var(--warn);
}
.state-mark--failed {
  background: var(--err-soft);
  color: var(--err);
}
@keyframes run-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .state-mark__spin {
    animation: none;
    border-right-color: currentColor;
  }
}
</style>
