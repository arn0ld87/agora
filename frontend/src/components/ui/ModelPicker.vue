<script setup lang="ts">
/**
 * ModelPicker — Wiederverwendbarer Provider/Modell-Selector.
 *
 * @deprecated Slice 5.5 — abgelöst durch v4 `AiModelPicker.vue`
 * (connection-basiert). Aktuell ohne Importeure (verwaist); als Read-Adapter
 * markiert, bis er in einem Folge-Slice gelöscht wird. Keine neuen Importeure.
 *
 * Props:
 *   modelValue: { provider_id, model_id } | null
 *   disabled?: boolean
 *   placeholder?: string
 *
 * Emit: update:modelValue
 *
 * Nutzt useAvailableModels für Live-Discovery. Keine hardcoded Listen.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAvailableModels } from '@/composables/useAvailableModels'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------
export interface ModelPickerValue {
  provider_id: string
  model_id: string
}

const props = withDefaults(
  defineProps<{
    modelValue: ModelPickerValue | null
    disabled?: boolean
    placeholder?: string
  }>(),
  {
    disabled: false,
    placeholder: undefined,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: ModelPickerValue | null): void
}>()

// ---------------------------------------------------------------------------
// i18n
// ---------------------------------------------------------------------------
const { t } = useI18n()

// ---------------------------------------------------------------------------
// Discovery
// ---------------------------------------------------------------------------
const { models, loading, error } = useAvailableModels()

// ---------------------------------------------------------------------------
// Computed: Gruppierung nach Provider (für <optgroup>)
// ---------------------------------------------------------------------------
interface ProviderGroup {
  provider_id: string
  provider_label: string
  models: Array<{ model_id: string; model_label: string }>
}

const groups = computed<ProviderGroup[]>(() => {
  const map = new Map<string, ProviderGroup>()
  for (const m of models.value) {
    let group = map.get(m.provider_id)
    if (!group) {
      group = {
        provider_id: m.provider_id,
        provider_label: m.provider_label,
        models: [],
      }
      map.set(m.provider_id, group)
    }
    group.models.push({ model_id: m.model_id, model_label: m.model_label })
  }
  // Reihenfolge ist bereits durch useAvailableModels sortiert (provider_label ASC, model_id ASC)
  return Array.from(map.values())
})

// Effektiver Placeholder-Text
const placeholderText = computed(
  () => props.placeholder ?? t('modelPicker.placeholder'),
)

// Aktuell ausgewählter Wert als serialisierter String für <select>
const selectedValue = computed<string>(() => {
  if (!props.modelValue) return ''
  return `${props.modelValue.provider_id}::${props.modelValue.model_id}`
})

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------
function handleChange(event: Event): void {
  const raw = (event.target as HTMLSelectElement).value
  if (!raw) {
    emit('update:modelValue', null)
    return
  }
  const sep = raw.indexOf('::')
  if (sep === -1) {
    emit('update:modelValue', null)
    return
  }
  emit('update:modelValue', {
    provider_id: raw.slice(0, sep),
    model_id: raw.slice(sep + 2),
  })
}
</script>

<template>
  <div class="model-picker">
    <!-- Loading-Zustand -->
    <div v-if="loading" class="model-picker__loading" aria-live="polite">
      <span class="model-picker__spinner" aria-hidden="true" />
      <span>{{ t('modelPicker.loading') }}</span>
    </div>

    <!-- Fehler-Zustand -->
    <div v-else-if="error" class="model-picker__error" role="alert">
      {{ t('modelPicker.error') }}: {{ error }}
    </div>

    <!-- Keine Modelle -->
    <div v-else-if="groups.length === 0" class="model-picker__empty">
      {{ t('modelPicker.noModels') }}
    </div>

    <!-- Normaler Selector -->
    <select
      v-else
      class="model-picker__select"
      :value="selectedValue"
      :disabled="disabled"
      @change="handleChange"
    >
      <option value="">{{ placeholderText }}</option>
      <optgroup
        v-for="group in groups"
        :key="group.provider_id"
        :label="group.provider_label"
      >
        <option
          v-for="m in group.models"
          :key="m.model_id"
          :value="`${group.provider_id}::${m.model_id}`"
        >
          {{ m.model_label }}
        </option>
      </optgroup>
    </select>
  </div>
</template>

<style scoped>
.model-picker {
  display: block;
  width: 100%;
}

.model-picker__select {
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-body, var(--fs-14));
  height: var(--ctl-h-md);
  padding: 0 36px 0 var(--ctl-pad-x);
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-pill));
  color: var(--text-primary, var(--fg));
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
  width: 100%;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.model-picker__select:hover {
  background: var(--surface-hover, var(--bg-glass-hi));
}

.model-picker__select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}

.model-picker__select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.model-picker__loading {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  font-size: var(--fs-footnote, var(--fs-12));
  color: var(--text-secondary, var(--fg-muted));
}

.model-picker__spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--hairline, var(--rule-strong));
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: mp-spin 0.7s linear infinite;
}

@keyframes mp-spin {
  to { transform: rotate(360deg); }
}

.model-picker__error {
  font-size: var(--fs-footnote, var(--fs-12));
  color: var(--color-red, #c0392b);
}

.model-picker__empty {
  font-size: var(--fs-footnote, var(--fs-12));
  color: var(--text-secondary, var(--fg-muted));
}
</style>
