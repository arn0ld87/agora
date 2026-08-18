<script setup lang="ts">
withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  mono?: boolean
  disabled?: boolean
  type?: 'text' | 'email' | 'password' | 'number'
}>(), {
  mono: false,
  disabled: false,
  type: 'text',
})

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <input
    class="v4-input v4-state-interactive"
    :class="{ 'v4-input--mono': mono }"
    :type="type"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
  />
</template>

<style scoped>
.v4-input {
  display: block;
  width: 100%;
  height: var(--ctl-h-md, 36px);
  padding: 0 12px;
  border-radius: var(--r-4, 8px);
  border: 1px solid var(--hairline);
  background: var(--surface-elevated);
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  outline: none;
  transition: border-color var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease),
    box-shadow var(--v4-state-motion-duration-fast) var(--v4-state-motion-ease);
  box-sizing: border-box;
}

.v4-input--mono {
  font-family: var(--font-mono);
}

.v4-input::placeholder {
  color: var(--text-tertiary);
}

/* Focus: übersteuert .v4-state-interactive mit komponentenspezifischem Inset-Ring */
.v4-input:focus-visible {
  border-color: var(--accent);
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: -2px;
}

/* Disabled: übersteuert .v4-state-interactive mit komponentenspezifischem BG */
.v4-input:disabled {
  background: var(--surface-inset);
}

/* Hover: komponentenspezifischer Border-Override */
.v4-input:hover:not(:focus-visible):not(:disabled) {
  border-color: var(--v4-state-hover-border);
}
</style>
