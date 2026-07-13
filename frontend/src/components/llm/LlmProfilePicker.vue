<!-- legacy-model-picker-allow: pre-5.5 v3 picker importer — see docs/epics/onboarding-provider-unification/slice-5-subplan.md (5.4 migrates, 5.5 removes) -->
<script setup lang="ts">
import { computed, onMounted, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLlmProfilesStore } from '../../store/llmProfiles'

const props = withDefaults(
  defineProps<{
    modelValue: string | null
    disabled?: boolean
    fallbackLabel?: string
    label?: string
  }>(),
  {
    disabled: false,
    fallbackLabel: undefined,
    label: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const { t } = useI18n()
const store = useLlmProfilesStore()

// Stable unique id for label/aria wiring.
const id = useId()
const hintId = `${id}-hint`

const resolvedLabel = computed(() => props.label ?? t('llmProfilePicker.label'))
const resolvedFallbackLabel = computed(
  () => props.fallbackLabel ?? t('llmProfilePicker.serverDefault'),
)

const options = computed(() => [
  { value: '', label: resolvedFallbackLabel.value },
  ...store.profiles.map((p) => ({
    value: p.id,
    label: `${p.name} — ${p.model_name}${p.is_default ? ` (${t('llmProfilePicker.defaultSuffix')})` : ''}`,
  })),
])

onMounted(async () => {
  // Only fetch when list is empty — avoid redundant requests on re-mount.
  if (store.profiles.length === 0) {
    try {
      await store.fetch()
    } catch {
      // error is set on store.error; we surface it in the template.
    }
  }
})

function onChange(e: Event) {
  const val = (e.target as HTMLSelectElement).value
  emit('update:modelValue', val || null)
}
</script>

<template>
  <div class="llm-profile-picker">
    <div class="llm-profile-picker__header">
      <label :for="id" class="llm-profile-picker__label">
        {{ resolvedLabel }}
      </label>
      <!-- named slot for use-site hint (e.g. "Für Persona-Generierung genutzt") -->
      <span v-if="$slots.hint" :id="hintId" class="llm-profile-picker__hint">
        <slot name="hint" />
      </span>
    </div>

    <p
      v-if="store.error"
      role="alert"
      class="llm-profile-picker__error"
    >
      {{ t('llmProfilePicker.error') }}
    </p>

    <div class="llm-profile-picker__select-wrap">
      <select
        :id="id"
        class="llm-profile-picker__select"
        :value="modelValue ?? ''"
        :disabled="disabled || store.loading"
        :aria-busy="store.loading ? 'true' : undefined"
        :aria-describedby="$slots.hint ? hintId : undefined"
        @change="onChange"
      >
        <option v-for="opt in options" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>

      <span v-if="store.loading" class="llm-profile-picker__loading" aria-live="polite">
        {{ t('llmProfilePicker.loading') }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.llm-profile-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.llm-profile-picker__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.llm-profile-picker__label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.llm-profile-picker__hint {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--text-secondary);
}

.llm-profile-picker__select-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.llm-profile-picker__select {
  width: 100%;
  appearance: none;
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-3, 6px);
  padding: 7px 10px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  outline: none;
  transition: border-color 80ms ease;
}

.llm-profile-picker__select:focus-visible {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.llm-profile-picker__select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.llm-profile-picker__loading {
  font-family: var(--font-sans);
  font-size: 11.5px;
  color: var(--text-secondary);
}

.llm-profile-picker__error {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--color-red, #c0392b);
  margin: 0;
  padding: 6px 10px;
  background: var(--surface-warning, #fff3f3);
  border-radius: var(--r-3, 6px);
  border: 1px solid var(--hairline);
}
</style>
