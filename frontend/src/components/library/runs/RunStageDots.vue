<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { STATE_GLYPH, type StageEntry } from '@/composables/library/runState'

/** Fuenf Stufenpunkte: Zeichen + Name + (fuer Screenreader) Zustand als Wort. */
defineProps<{ stages: StageEntry[] }>()
const { t } = useI18n()
</script>

<template>
  <ul class="stage-dots" :aria-label="t('views.library.runs.stage.list')">
    <li v-for="s in stages" :key="s.key" class="stage-dots__item" :data-stage="s.key" :data-state="s.state">
      <span class="stage-dots__dot" :class="`stage-dots__dot--${s.state}`" aria-hidden="true">
        <span v-if="s.state === 'running'" class="stage-dots__spin" />
        <template v-else>{{ STATE_GLYPH[s.state] }}</template>
      </span>
      <span class="stage-dots__name">{{ t(`views.library.runs.stage.${s.key}`) }}</span>
      <span class="sr-only">{{ t(`views.library.runs.state.${s.state}`) }}</span>
    </li>
  </ul>
</template>

<style scoped>
.stage-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.stage-dots__item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--fg2);
}
.stage-dots__dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  color: var(--fg2);
}
.stage-dots__dot--done {
  color: var(--ok);
}
.stage-dots__dot--incomplete,
.stage-dots__dot--budget {
  color: var(--warn);
}
.stage-dots__dot--failed {
  color: var(--err);
}
.stage-dots__dot--running {
  color: var(--fg);
}
.stage-dots__spin {
  width: 10px;
  height: 10px;
  box-sizing: border-box;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  animation: stage-spin 0.9s linear infinite;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
@keyframes stage-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .stage-dots__spin {
    animation: none;
    border-right-color: currentColor;
  }
}
</style>
