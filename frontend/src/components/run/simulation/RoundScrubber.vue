<script setup lang="ts">
/**
 * Rundenregler (#1801): „Live" (Cursor `null`) oder Runde 1…max. Die
 * „Neue Beiträge"-Pille erscheint, wenn im Rückblick Live-Beiträge gesammelt
 * wurden, und bleibt, bis sie angeklickt wird (kein stilles Verschwinden, die
 * Liste springt nicht).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  /** `null` = live. */
  cursor: number | null
  /** Höchste bekannte Runde; `null`, wenn keine Rundenangabe vorliegt. */
  maxRound: number | null
  pendingCount: number
}>()
const emit = defineEmits<{ 'update:cursor': [round: number | null]; flush: [] }>()
const { t } = useI18n()

const hasRounds = computed(() => props.maxRound !== null && props.maxRound >= 1)
const sliderValue = computed(() => props.cursor ?? props.maxRound ?? 1)

function onInput(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isInteger(value)) emit('update:cursor', value)
}
</script>

<template>
  <div class="scrub" data-testid="round-scrubber">
    <span class="scrub__label" id="scrub-label">{{ t('views.run.simFeed.scrubber.label') }}</span>
    <button
      type="button"
      class="scrub__live"
      :aria-pressed="cursor === null"
      data-testid="scrubber-live"
      @click="emit('update:cursor', null)"
    >
      {{ t('views.run.simFeed.scrubber.live') }}
    </button>
    <label v-if="hasRounds" class="scrub__slider">
      <span class="sr-only">{{ t('views.run.simFeed.scrubber.slider') }}</span>
      <input
        type="range"
        min="1"
        :max="maxRound ?? 1"
        step="1"
        :value="sliderValue"
        :aria-valuetext="t('views.run.simFeed.scrubber.status', { round: sliderValue, max: maxRound ?? 1 })"
        data-testid="scrubber-range"
        @input="onInput"
      />
    </label>
    <span class="scrub__status" role="status" data-testid="scrubber-status">
      <template v-if="!hasRounds">{{ t('views.run.simFeed.scrubber.noRounds') }}</template>
      <template v-else-if="cursor === null">{{ t('views.run.simFeed.scrubber.liveHint') }}</template>
      <template v-else>{{ t('views.run.simFeed.scrubber.status', { round: cursor, max: maxRound ?? cursor }) }}</template>
    </span>
    <button
      v-if="pendingCount > 0"
      type="button"
      class="scrub__pill"
      data-testid="scrubber-pill"
      @click="emit('flush')"
    >
      {{ t('views.run.simFeed.scrubber.pill', { count: pendingCount }) }}
    </button>
  </div>
</template>

<style scoped>
.scrub {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
  font-size: 13px;
}
.scrub__label {
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.scrub__live,
.scrub__pill {
  height: 28px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.scrub__live[aria-pressed='true'] {
  border-color: var(--acc);
  background: var(--acc);
  color: var(--on-acc);
}
.scrub__pill {
  border-color: var(--acc);
  color: var(--acc);
}
.scrub__live:focus-visible,
.scrub__pill:focus-visible,
.scrub__slider input:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.scrub__slider {
  display: inline-flex;
  flex: 1 1 160px;
  min-width: 120px;
}
.scrub__slider input {
  width: 100%;
}
.scrub__status {
  color: var(--fg2);
  font-size: 12px;
}
</style>
