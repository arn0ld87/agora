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
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-footnote, var(--fs-12));
  letter-spacing: 0;
  text-transform: none;
  color: var(--text-secondary, var(--fg-muted));
  font-weight: 590;
}
.req { color: var(--accent); margin-left: 4px; }
.input {
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-body, var(--fs-14));
  height: var(--ctl-h-md);
  padding: 0 var(--ctl-pad-x);
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-pill));
  color: var(--text-primary, var(--fg));
  outline: none;
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
  width: 100%;
}
.input:hover { background: var(--surface-hover, var(--bg-glass-hi)); }
.input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}
.input::placeholder { color: var(--text-tertiary, var(--fg-meta)); }
.hint {
  margin: 0;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-footnote, 12px);
  letter-spacing: 0;
  color: var(--text-tertiary, var(--fg-meta));
}
</style>
