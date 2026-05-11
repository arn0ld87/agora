<script setup lang="ts">
defineProps<{
  modelValue: string
  options: Array<{ value: string; label: string }>
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="v4-segmented" role="group">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="v4-segmented__seg"
      :class="{ 'v4-segmented__seg--active': modelValue === opt.value }"
      @click="$emit('update:modelValue', opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.v4-segmented {
  display: inline-flex;
  background: var(--surface-inset, var(--gray-6, #f2f2f7));
  padding: 2px;
  border-radius: var(--r-pill, 999px);
  gap: 0;
}

.v4-segmented__seg {
  height: var(--ctl-h-sm, 28px);
  padding: 0 12px;
  border-radius: var(--r-pill, 999px);
  border: none;
  background: transparent;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 120ms ease, background 120ms ease, box-shadow 120ms ease;
  white-space: nowrap;
  line-height: 1;
}

.v4-segmented__seg:hover:not(.v4-segmented__seg--active) {
  color: var(--text-primary);
}

.v4-segmented__seg--active {
  background: #fff;
  box-shadow: var(--shadow-control, 0 1px 3px rgba(0, 0, 0, 0.12), 0 0 0 0.5px rgba(0, 0, 0, 0.04));
  color: var(--text-primary);
}
</style>
