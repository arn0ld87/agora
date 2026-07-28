<script setup lang="ts">
/**
 * EnvSetupModelPanel — Modell-/Sprach-Auswahl (Step 2).
 */
import { useI18n } from 'vue-i18n'
import Select from '../ui/Select.vue'
import AiModelPicker from '../v4/forms/AiModelPicker.vue'
import type { AiModelRef } from '@/contracts/aiModelRef'

const { t } = useI18n()

defineProps({
  language: { type: String, required: true },
  agentToolsEnabled: { type: Boolean, default: false },
  maxToolCallsPerAction: { type: Number, default: 0 },
  modelRef: { type: Object as () => AiModelRef | null, default: null },
})

const emit = defineEmits<{
  'update:language': [value: string]
  'update:modelRef': [value: AiModelRef | null]
}>()
</script>

<template>
  <div class="env-setup-model-panel">
    <p v-if="agentToolsEnabled" class="hint warning">
      {{ t('step2.agentTools.warning', { count: maxToolCallsPerAction }) }}
    </p>

    <div class="setup-grid">
      <!-- Kanonische Modell-Auswahl (AiModelRef) -->
      <div class="setup-cell setup-cell--wide">
        <label class="field-label">{{ t('step2.model.label') }}</label>
        <AiModelPicker
          :model-value="modelRef"
          mode="chat"
          @update:model-value="emit('update:modelRef', $event)"
        />
      </div>

      <!-- Agent language -->
      <div class="setup-cell">
        <Select
          :model-value="language"
          :label="t('step2.language.label')"
          :options="[
            { value: 'de', label: t('step2.language.de') },
            { value: 'en', label: t('step2.language.en') },
          ]"
          @update:model-value="emit('update:language', $event)"
        />
        <p class="hint">{{ t('step2.language.hint') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.setup-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--s-5) var(--s-7);
}
.setup-cell { display: flex; flex-direction: column; gap: var(--s-2); }
.setup-cell--wide { grid-column: 1 / -1; }
.field-label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin: 0;
}

@media (max-width: 720px) {
  .setup-grid { grid-template-columns: 1fr; }
}

.setup-cell {
  background: var(--surface-inset, var(--bg-elevated));
  border-radius: var(--r-6, var(--r-1));
}
.hint {
  color: var(--text-secondary, var(--fg-muted));
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
</style>
