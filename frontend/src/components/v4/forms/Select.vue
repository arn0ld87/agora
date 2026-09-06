<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string
  options: Array<{ value: string; label: string }>
  placeholder?: string
  disabled?: boolean
  /** Sichtbares Feldlabel (label-Typo, kein Uppercase). Optional — ohne
   * Label bleibt der Select ein reines Formularelement. */
  label?: string
  /** Sternchen-Marker neben dem Label für Pflichtfelder. */
  required?: boolean
}>(), {
  disabled: false,
  label: undefined,
  required: false,
})

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="v4-select-field">
    <label v-if="label" class="v4-select-label">
      {{ label }}<span v-if="required" class="v4-select-required">*</span>
    </label>
    <div class="v4-select-wrap" :class="{ 'v4-select-wrap--disabled': disabled }">
      <select
        class="v4-select v4-state-interactive"
        :value="modelValue"
        :disabled="disabled"
        :aria-label="label"
        @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
      >
        <option v-if="placeholder && !modelValue" value="" disabled selected>
          {{ placeholder }}
        </option>
        <option
          v-for="opt in options"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
        </option>
      </select>
      <!-- Inline-SVG chevron-down (kein Slice-B-Icon-Dep) -->
      <span class="v4-select-chevron" aria-hidden="true">
        <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
          <path
            d="M4 7 L10 13 L16 7"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </span>
    </div>
  </div>
</template>

<style scoped>
.v4-select-field {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1, 4px);
}

/* label-Typo-Rolle (Audit §Typografie): 11.5px/1.3, Gewicht 500,
   Tracking 0.02em, kein Uppercase. */
.v4-select-label {
  font-family: var(--font-sans);
  font-size: var(--fs-label, 11.5px);
  line-height: var(--lh-label, 1.3);
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: none;
  color: var(--text-secondary);
}

.v4-select-required {
  color: var(--accent);
  margin-left: 4px;
}

.v4-select-wrap {
  position: relative;
  display: block;
}

.v4-select-wrap--disabled {
  opacity: 0.4;
  pointer-events: none;
}

.v4-select {
  display: block;
  width: 100%;
  height: var(--ctl-h-md, 32px);
  padding: 0 36px 0 12px;
  border-radius: var(--r-3, 6px);
  border: 1px solid var(--hairline);
  background-color: var(--surface-inset, var(--surface-elevated));
  /* eigener Chevron kommt aus dem <span>; die globale native-select-Regel
     in global.css setzt sonst zusätzlich ein Chevron-background-image. */
  background-image: none;
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
  transition: border-color var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    box-shadow var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
  box-sizing: border-box;
}

/* Focus: Inset-Ring Override */
.v4-select:focus-visible {
  border-color: var(--accent);
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: -2px;
}

/* Hover: komponentenspezifischer Border-Override */
.v4-select:hover:not(:focus-visible) {
  border-color: var(--v4-state-hover-border);
}

.v4-select-chevron {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
}
</style>
