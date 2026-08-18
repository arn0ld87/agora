<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string
  options: Array<{ value: string; label: string }>
  placeholder?: string
  disabled?: boolean
}>(), {
  disabled: false,
})

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="v4-select-wrap" :class="{ 'v4-select-wrap--disabled': disabled }">
    <select
      class="v4-select v4-state-interactive"
      :value="modelValue"
      :disabled="disabled"
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
</template>

<style scoped>
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
  height: var(--ctl-h-md, 36px);
  padding: 0 36px 0 12px;
  border-radius: var(--r-4, 8px);
  border: 1px solid var(--hairline);
  background: var(--surface-elevated);
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
