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
    class="v4-input"
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
  background: var(--surface-elevated, #fff);
  font-family: var(--font-sans);
  font-size: var(--fs-callout, 14px);
  color: var(--text-primary);
  outline: none;
  transition: border-color 150ms ease, box-shadow 150ms ease;
  box-sizing: border-box;
}

.v4-input--mono {
  font-family: var(--font-mono);
}

.v4-input::placeholder {
  color: var(--text-tertiary);
}

.v4-input:focus {
  border-color: var(--accent);
  outline: 2px solid var(--focus-ring);
  outline-offset: -2px;
}

.v4-input:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  background: var(--surface-inset, #f2f2f7);
}

.v4-input:hover:not(:focus):not(:disabled) {
  border-color: var(--text-tertiary);
}
</style>
