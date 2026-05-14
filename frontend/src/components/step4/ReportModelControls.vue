<script setup lang="ts">
import { computed } from 'vue'
import Btn from '../ui/Btn.vue'
import Select from '../ui/Select.vue'

interface Option {
  value: string
  label: string
}

interface Props {
  reportModelOption: string
  customReportModel: string
  modelOptions: Option[]
  isRegenerating: boolean
  provider: string
  apiKey: string
  baseUrl: string
  providerOptions: Option[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:reportModelOption': [value: string]
  'update:customReportModel': [value: string]
  'update:provider': [value: string]
  'update:apiKey': [value: string]
  'update:baseUrl': [value: string]
  regenerate: []
}>()

const selectedModel = computed({
  get: () => props.reportModelOption,
  set: (value: string) => emit('update:reportModelOption', value),
})

const customModel = computed({
  get: () => props.customReportModel,
  set: (value: string) => emit('update:customReportModel', value),
})

const provider = computed({
  get: () => props.provider,
  set: (value: string) => emit('update:provider', value),
})

const apiKey = computed({
  get: () => props.apiKey,
  set: (value: string) => emit('update:apiKey', value),
})

const baseUrl = computed({
  get: () => props.baseUrl,
  set: (value: string) => emit('update:baseUrl', value),
})

const providerEnabled = computed(() => provider.value !== 'default')
</script>

<template>
  <div class="model-row">
    <div class="model-cell">
      <Select
        v-model="selectedModel"
        label="Modell für Report"
        :options="modelOptions"
      />
    </div>
    <div v-if="reportModelOption === 'custom'" class="model-cell">
      <label class="field-label">Eigenes Modell</label>
      <input
        v-model="customModel"
        class="model-input"
        type="text"
        placeholder="z. B. deepseek-v3.2:cloud"
      />
    </div>
    <div class="model-cell">
      <Select
        v-model="provider"
        label="LLM-Anbieter"
        :options="providerOptions"
      />
    </div>
    <div v-if="providerEnabled" class="model-cell">
      <label class="field-label">API-Key</label>
      <input
        v-model="apiKey"
        class="model-input"
        type="password"
        placeholder="API-Key für gewählten Anbieter"
      />
    </div>
    <div v-if="providerEnabled" class="model-cell">
      <label class="field-label">Base-URL (optional)</label>
      <input
        v-model="baseUrl"
        class="model-input"
        type="text"
        placeholder="z. B. https://api.openai.com/v1"
      />
    </div>
    <Btn
      variant="ghost"
      :loading="isRegenerating"
      :disabled="isRegenerating"
      @click="emit('regenerate')"
    >
      Neu generieren
    </Btn>
  </div>
</template>

<style scoped>
.model-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
.model-input {
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  color: var(--fg);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 8px 10px;
  outline: none;
}
.model-input:focus {
  border-color: var(--accent);
}
@media (max-width: 720px) {
  .model-row {
    grid-template-columns: 1fr;
  }
}
</style>
