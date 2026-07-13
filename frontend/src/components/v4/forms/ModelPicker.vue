<!-- legacy-model-picker-allow: pre-5.5 v3 picker importer — see docs/epics/onboarding-provider-unification/slice-5-subplan.md (5.4 migrates, 5.5 removes) -->
<script setup lang="ts">
/**
 * ModelPicker — wählt eine LLM-Route (Provider + Modell) per Dropdown.
 *
 * - Zeigt OptGroups je Provider an, sortiert alphabetisch nach Provider-Label.
 * - Versteckt Provider ohne hinterlegten API-Key (Ausnahme: Ollama + Copilot,
 *   die auch ohne expliziten Key benutzbar sein können).
 * - Emit `update:modelValue` mit der gewählten ``StageLLMRoute`` oder ``null``
 *   für „nichts gewählt / nutze Default des Eltern-Kontextes".
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useLlmProvidersStore } from '@/store/llmProviders'
import type { StageLLMRoute } from '@/contracts/llmRoutingContract'

const props = withDefaults(defineProps<{
  modelValue?: StageLLMRoute | null
  placeholder?: string
  disabled?: boolean
}>(), {
  modelValue: null,
  placeholder: 'Modell wählen …',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: StageLLMRoute | null]
}>()

const store = useLlmProvidersStore()
const loadingModels = ref<Record<string, boolean>>({})

// Ollama Cloud BRAUCHT einen Bearer-Token (OLLAMA_API_KEY), darf also NICHT
// in dieser Liste stehen. Nur Provider mit Token-Auflösung über Sub-Module
// (z. B. ``github_copilot.resolve_copilot_token``) bleiben hier drin.
const PROVIDERS_WITHOUT_KEY = new Set(['github_copilot'])

const availableProviders = computed(() =>
  store.providers.filter((p) =>
    PROVIDERS_WITHOUT_KEY.has(p.type) || store.hasKey(p.id),
  ),
)

onMounted(async () => {
  if (store.providers.length === 0) {
    await store.loadProviders()
  }
  for (const p of availableProviders.value) {
    if (!(p.id in store.models)) {
      void hydrateModels(p.id)
    }
  }
})

watch(
  () => availableProviders.value.map((p) => p.id).join(','),
  (key) => {
    if (!key) return
    for (const p of availableProviders.value) {
      if (!(p.id in store.models)) {
        void hydrateModels(p.id)
      }
    }
  },
)

async function hydrateModels(providerId: string): Promise<void> {
  loadingModels.value = { ...loadingModels.value, [providerId]: true }
  try {
    await store.fetchModels(providerId)
  } catch (err) {
    // Fehler landet im store.lastError — wir lassen die Option leer, kein Throw
    console.warn('ModelPicker: fetchModels failed', providerId, err)
  } finally {
    loadingModels.value = { ...loadingModels.value, [providerId]: false }
  }
}

const selectedValue = computed(() => {
  if (!props.modelValue?.provider_id || !props.modelValue?.model) return ''
  return `${props.modelValue.provider_id}::${props.modelValue.model}`
})

function onChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  const raw = target.value
  if (!raw) {
    emit('update:modelValue', null)
    return
  }
  const sep = raw.indexOf('::')
  if (sep < 0) return
  const providerId = raw.slice(0, sep)
  const model = raw.slice(sep + 2)
  emit('update:modelValue', {
    stage: null,
    provider_id: providerId,
    model,
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  })
}
</script>

<template>
  <div class="model-picker">
    <select
      class="model-picker__select"
      :disabled="disabled"
      :value="selectedValue"
      @change="onChange"
    >
      <option value="">{{ placeholder }}</option>
      <template v-for="provider in availableProviders" :key="provider.id">
        <optgroup :label="provider.label">
          <option
            v-for="model in (store.models[provider.id]?.models ?? []).map(m => m.id)"
            :key="`${provider.id}::${model}`"
            :value="`${provider.id}::${model}`"
          >
            {{ model }}
          </option>
          <option
            v-if="(store.models[provider.id]?.models ?? []).length === 0 && (provider.fallback_models ?? []).length"
            disabled
          >
            (Modelle laden …)
          </option>
        </optgroup>
      </template>
    </select>
  </div>
</template>

<style scoped>
.model-picker {
  display: block;
  min-width: 220px;
}
.model-picker__select {
  width: 100%;
  height: var(--ctl-h-md, 36px);
  padding: 0 32px 0 12px;
  border-radius: var(--r-4, 8px);
  border: 1px solid var(--hairline);
  background: var(--surface-elevated, #fff);
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  cursor: pointer;
}
.model-picker__select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
