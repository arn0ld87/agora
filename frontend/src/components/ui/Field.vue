<script setup>
defineProps({
  label: { type: String, required: true },
  modelValue: { type: [String, Number], default: '' },
  type: { type: String, default: 'text' },
  placeholder: { type: String, default: '' },
  required: { type: Boolean, default: false },
  hint: { type: String, default: '' },
})
defineEmits(['update:modelValue'])
</script>

<template>
  <div class="field">
    <label>{{ label }}<span v-if="required" class="req">*</span></label>
    <input
      class="input"
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      @input="$emit('update:modelValue', $event.target.value)"
    >
    <p v-if="hint" class="hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.field { display: flex; flex-direction: column; gap: var(--s-2); }
label {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.req { color: var(--accent); margin-left: 4px; }
.input {
  font-family: var(--ff-sans);
  font-size: var(--fs-18);
  padding: 12px 0;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  color: var(--fg);
  outline: none;
  transition: border-color 150ms ease;
  width: 100%;
}
.input:focus { border-bottom-color: var(--accent); }
.input::placeholder { color: var(--fg-meta); }
.hint {
  margin: 0;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-meta);
}
</style>
