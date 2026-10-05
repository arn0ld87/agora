<script setup lang="ts">
import { useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { ActivityModeSchema, type ActivityMode } from '../../contracts/simulationActivityContract'

const { t } = useI18n()

defineProps({
  modelValue: { type: String as () => ActivityMode, required: true },
  isPreparing: { type: Boolean, default: false },
})

const emit = defineEmits<{ (e: 'update:modelValue', value: ActivityMode): void }>()

const modes = ActivityModeSchema.options
const groupId = useId()

function onChange(event: Event) {
  const parsed = ActivityModeSchema.safeParse((event.target as HTMLInputElement).value)
  if (parsed.success) emit('update:modelValue', parsed.data)
}
</script>

<template>
  <fieldset class="activity-mode-field" :disabled="isPreparing">
    <legend class="activity-mode-label">{{ t('step2.activityMode.label') }}</legend>
    <label v-for="mode in modes" :key="mode" class="activity-mode-option">
      <input
        type="radio"
        :name="`activity-mode-${groupId}`"
        :value="mode"
        :checked="modelValue === mode"
        :aria-describedby="`${groupId}-${mode}-hint`"
        @change="onChange"
      />
      <span class="activity-mode-text">
        <span>{{ t(`step2.activityMode.${mode}.label`) }}</span>
        <small :id="`${groupId}-${mode}-hint`" class="hint">
          {{ t(`step2.activityMode.${mode}.hint`) }}
        </small>
      </span>
    </label>
  </fieldset>
</template>

<style scoped>
.activity-mode-field {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.activity-mode-label {
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg);
  padding: 0;
  margin-bottom: var(--s-2);
}
.activity-mode-option {
  display: flex;
  align-items: flex-start;
  gap: var(--s-3);
  cursor: pointer;
  font-family: var(--font-sans);
  font-size: var(--fs-16);
  color: var(--fg);
}
.activity-mode-option input { accent-color: var(--accent); margin-top: 4px; }
.activity-mode-text { display: flex; flex-direction: column; gap: 2px; }
.hint {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--fg-muted);
}
</style>
