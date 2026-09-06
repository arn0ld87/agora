<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Select from '../v4/forms/Select.vue'
import { DEFAULT_REPORT_MODE, type ReportMode } from '../../contracts/reportV3Contract'

interface Props {
  modelValue?: ReportMode
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: DEFAULT_REPORT_MODE,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [mode: ReportMode]
}>()

const { t } = useI18n()

const selectedMode = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value as ReportMode),
})

const modeOptions = computed(() => [
  { value: 'strict', label: t('reportMode.strict.label') },
  { value: 'balanced', label: t('reportMode.balanced.label') },
  { value: 'explorative', label: t('reportMode.explorative.label') },
])
</script>

<template>
  <div class="mode-row" :class="{ 'is-disabled': disabled }">
    <div class="mode-cell">
      <Select
        v-model="selectedMode"
        :label="t('reportMode.label')"
        :options="modeOptions"
        :disabled="disabled"
      />
      <p class="mode-hint">{{ t(`reportMode.${selectedMode}.hint`) }}</p>
    </div>
  </div>
</template>

<style scoped>
.mode-row {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--s-3);
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.mode-row.is-disabled {
  opacity: 0.5;
  pointer-events: none;
}
.mode-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.mode-hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
  margin: 0;
}
</style>
