<script setup lang="ts" generic="T extends string">
/**
 * SegmentedChoice — segmentierte Auswahl als Radiogruppe (role="radiogroup",
 * Pfeiltasten wechseln und setzen die Auswahl, Roving-Tabindex).
 */
import { nextTick, ref } from 'vue'

const props = defineProps<{
  modelValue: T
  options: ReadonlyArray<{ value: T; label: string }>
  /** Zugänglicher Name der Gruppe. */
  label: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: T] }>()

const buttons = ref<HTMLButtonElement[]>([])

function select(value: T): void {
  if (value !== props.modelValue) emit('update:modelValue', value)
}

async function onKey(event: KeyboardEvent, index: number): Promise<void> {
  const last = props.options.length - 1
  let next: number
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = index === last ? 0 : index + 1
  else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = index === 0 ? last : index - 1
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = last
  else return
  event.preventDefault()
  select(props.options[next].value)
  await nextTick()
  buttons.value[next]?.focus()
}
</script>

<template>
  <div class="segmented" role="radiogroup" :aria-label="label">
    <button
      v-for="(opt, i) in options"
      :key="opt.value"
      :ref="(el) => { if (el) buttons[i] = el as HTMLButtonElement }"
      type="button"
      role="radio"
      class="segmented__option"
      :aria-checked="opt.value === modelValue"
      :tabindex="opt.value === modelValue ? 0 : -1"
      @click="select(opt.value)"
      @keydown="onKey($event, i)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented {
  display: inline-flex;
  padding: 2px;
  gap: 2px;
  background: var(--s2);
  border: 1px solid var(--line);
  border-radius: var(--ag-r-10);
}

.segmented__option {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  padding: 5px 12px;
  border-radius: var(--ag-r-8);
  cursor: pointer;
}

.segmented__option:hover {
  color: var(--fg);
}

.segmented__option[aria-checked='true'] {
  background: var(--acc);
  color: var(--on-acc);
}

.segmented__option:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
</style>
