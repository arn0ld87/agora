<script setup>
defineProps({
  label: { type: String, required: true },
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  required: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>

<template>
  <div class="field">
    <label>{{ label }}<span v-if="required" class="req">*</span></label>
    <select
      class="select"
      :value="modelValue"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option v-for="opt in options" :key="(typeof opt === 'object' ? opt.value : opt)" :value="(typeof opt === 'object' ? opt.value : opt)">
        {{ typeof opt === 'object' ? opt.label : opt }}
      </option>
    </select>
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
.select {
  font-family: var(--ff-sans);
  font-size: var(--fs-18);
  padding: 12px 28px 12px 0;
  background: transparent
    url("data:image/svg+xml,%3Csvg width='12' height='8' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%230d0c0c' stroke-width='1.5' fill='none'/%3E%3C/svg%3E")
    no-repeat right 4px center;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  color: var(--fg);
  outline: none;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
  transition: border-color 150ms ease;
}
.select:focus { border-bottom-color: var(--accent); }
</style>
