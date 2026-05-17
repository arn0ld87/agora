<script setup lang="ts">
/**
 * ReportModelControls — Auswahl des LLM-Modells für die Report-Regenerierung.
 *
 * Slice A1 (2026-05-17): Migrationsendzustand. Nutzt projektweit denselben
 * ModelPicker wie das Workspace-Default-Dropdown unter `/settings/llm-providers`.
 * Provider+API-Key+Base-URL werden NICHT mehr inline gepflegt — Keys laufen
 * über den ``LlmProviderSecretsStore`` (Settings-Seite), das Backend zieht
 * sie via ``SecretResolver`` und ``build_route_subprocess_env`` automatisch.
 * Lokale Ollama-Modelle erscheinen, sobald ein Ollama- oder
 * OpenAI-kompatibler Provider mit passender ``base_url`` in
 * ``/settings/llm-providers`` hinterlegt ist.
 */
import { useI18n } from 'vue-i18n'
import Button from '@/components/v4/forms/Button.vue'
import ModelPicker from '@/components/v4/forms/ModelPicker.vue'
import type { StageLLMRoute } from '@/contracts/llmRoutingContract'

const { t } = useI18n()

defineProps<{
  modelValue: StageLLMRoute | null
  isRegenerating: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: StageLLMRoute | null]
  regenerate: []
}>()
</script>

<template>
  <div class="model-row">
    <div class="model-cell model-cell--picker">
      <label class="field-label">{{ t('step4.model.reportLabel') }}</label>
      <ModelPicker
        :model-value="modelValue"
        :placeholder="t('step4.model.placeholder', 'Modell wählen …')"
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
