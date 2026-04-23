<template>
  <div class="workspace-mode-switch">
    <button
      v-for="mode in modes"
      :key="mode.value"
      class="switch-btn"
      :class="{ active: currentMode === mode.value }"
      @click="$emit('update:mode', mode.value)"
    >
      {{ mode.label }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  currentMode: {
    type: String,
    required: true,
  },
  modes: {
    type: Array,
    default: () => [],
  },
})

defineEmits(['update:mode'])
</script>

<style scoped>
.workspace-mode-switch {
  display: inline-flex;
  justify-self: center;
  gap: var(--s-2);
  padding: 4px;
  background: var(--paper-1);
  border-radius: var(--r-1);
}

.switch-btn {
  border: 0;
  background: transparent;
  padding: 6px 14px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  border-radius: var(--r-1);
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}

.switch-btn:hover {
  color: var(--ink-0);
}

.switch-btn.active {
  background: var(--paper-0);
  color: var(--ink-0);
  border: 1px solid var(--rule);
}

@media (max-width: 720px) {
  .workspace-mode-switch {
    justify-self: start;
  }
}
</style>
