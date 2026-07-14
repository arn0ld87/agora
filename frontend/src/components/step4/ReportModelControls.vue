<script setup lang="ts">
/**
 * ReportModelControls — Auswahl des LLM-Modells für die Report-Regenerierung.
 *
 * Slice 7.6b: Migration auf den kanonischen AiModelPicker (v4/forms/AiModelPicker).
 * Der Vertrag ist jetzt AiModelRef (provider_connection_id + model_id). Der Parent
 * (Step4Report) konvertiert via useAiModelRefAdapter, wenn er den llm_model-String
 * an das Backend uebergibt (Run-Snapshot bleibt vertragsgleich).
 */
import { useI18n } from 'vue-i18n'
import Button from '@/components/v4/forms/Button.vue'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

defineProps<{
  modelValue: AiModelRef | null
  isRegenerating: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AiModelRef | null]
  regenerate: []
}>()
</script>

<template>
  <div class="model-row">
    <div class="model-cell model-cell--picker">
      <label class="field-label">{{ t('step4.model.reportLabel') }}</label>
      <AiModelPicker
        :model-value="modelValue"
        mode="chat"
        :placeholder="t('step4.model.placeholder')"
        @update:model-value="(value) => emit('update:modelValue', value)"
      />
    </div>
    <Button
      variant="ghost"
      :loading="isRegenerating"
      :disabled="isRegenerating"
      @click="emit('regenerate')"
    >
      {{ t('step4.model.regenerate') }}
    </Button>
  </div>
</template>

<style scoped>
.model-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  gap: var(--s-3);
  align-items: end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.model-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.field-label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
@media (max-width: 720px) {
  .model-row {
    grid-template-columns: 1fr;
  }
}
</style>
