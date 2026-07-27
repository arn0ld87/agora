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
    <span class="select-wrap">
      <!-- Das sichtbare <label> ist nicht per for/id mit dem <select>
           verknuepft (es liegt ausserhalb von .select-wrap), der Select hatte
           dadurch keinen accessible name — axe-core select-name, critical
           (Issue #838). aria-label spiegelt exakt den sichtbaren Labeltext. -->
      <select
        class="select"
        :aria-label="label"
        :value="modelValue"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option
          v-for="opt in options"
          :key="(typeof opt === 'object' ? opt.value : opt)"
          :value="(typeof opt === 'object' ? opt.value : opt)"
        >
          {{ typeof opt === 'object' ? opt.label : opt }}
        </option>
      </select>
    </span>
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
.select-wrap { position: relative; display: block; }
.select-wrap::after {
  content: "";
  position: absolute;
  right: 16px;
  top: 50%;
  width: 8px;
  height: 8px;
  border-right: 1.5px solid var(--text-secondary, var(--fg-muted));
  border-bottom: 1.5px solid var(--text-secondary, var(--fg-muted));
  transform: translateY(-65%) rotate(45deg);
  pointer-events: none;
}
.select {
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
  transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease;
}
.select:hover { background: var(--surface-hover, var(--bg-glass-hi)); }
.select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}
</style>
