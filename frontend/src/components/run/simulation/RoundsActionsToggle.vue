<script setup lang="ts">
/**
 * Umschalter „Runden | Aktionen“ (Radiogruppe mit Pfeiltasten, Roving-Tabindex).
 */
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'

export type RoundsView = 'rounds' | 'actions'

const props = defineProps<{ modelValue: RoundsView }>()
const emit = defineEmits<{ 'update:modelValue': [value: RoundsView] }>()

const { t } = useI18n()
const OPTIONS: RoundsView[] = ['rounds', 'actions']
const buttons = ref<HTMLElement[]>([])

function select(value: RoundsView): void {
  if (value !== props.modelValue) emit('update:modelValue', value)
}

function onKeydown(event: KeyboardEvent, index: number): void {
  let next = index
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % OPTIONS.length
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + OPTIONS.length) % OPTIONS.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = OPTIONS.length - 1
  else return
  event.preventDefault()
  select(OPTIONS[next]!)
  void nextTick(() => buttons.value[next]?.focus())
}
</script>

<template>
  <div class="rat" role="radiogroup" :aria-label="t('views.run.simRounds.viewLabel')" data-testid="rounds-actions-toggle">
    <button
      v-for="(option, index) in OPTIONS"
      :key="option"
      :ref="(el) => { if (el) buttons[index] = el as HTMLElement }"
      type="button"
      role="radio"
      class="rat__option"
      :class="{ 'rat__option--active': modelValue === option }"
      :aria-checked="modelValue === option"
      :tabindex="modelValue === option ? 0 : -1"
      :data-testid="`rounds-view-${option}`"
      @click="select(option)"
      @keydown="onKeydown($event, index)"
    >
      {{ t(option === 'rounds' ? 'views.run.simRounds.viewRounds' : 'views.run.simRounds.viewActions') }}
    </button>
  </div>
</template>

<style scoped>
.rat {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.rat__option {
  height: 28px;
  padding: 0 12px;
  border: none;
  border-radius: var(--ag-r-6);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.rat__option:hover { color: var(--fg); }
.rat__option--active { background: var(--s3); color: var(--fg); font-weight: 650; }
.rat__option:focus-visible { outline: 2px solid var(--acc-line); outline-offset: 2px; }
</style>
