<template>
  <div class="workspace-mode-switch" role="group">
    <button
      v-for="mode in modes"
      :key="mode.value"
      type="button"
      class="switch-btn"
      :class="{ active: currentMode === mode.value, 'is-active': currentMode === mode.value }"
      :aria-pressed="currentMode === mode.value"
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
  align-items: center;
  height: var(--ctl-h-md, 32px);
  gap: 0;
  padding: 2px;
  background: var(--surface-inset, var(--bg-elevated));
  border-radius: var(--r-4, var(--r-1));
  box-shadow: inset 0 0 0 1px var(--hairline, var(--rule));
}

.switch-btn {
  position: relative;
  height: 28px;
  border: 0;
  background: transparent;
  padding: 0 14px;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-subhead, var(--fs-13));
  font-weight: 500;
  letter-spacing: 0;
  color: var(--text-primary, var(--fg));
  border-radius: var(--r-3, var(--r-1));
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease, box-shadow 150ms ease;
}

.switch-btn + .switch-btn::before {
  content: "";
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 1px;
  background: var(--hairline, var(--rule));
}

.switch-btn:hover {
  background: var(--surface-hover, rgba(0,0,0,0.04));
}

.switch-btn.active {
  background: var(--surface-elevated, var(--bg));
  color: var(--text-primary, var(--fg));
  box-shadow: 0 1px 2px rgba(0,0,0,0.08), 0 0 0 0.5px rgba(0,0,0,0.04);
  font-weight: 600;
}

.switch-btn.active::before,
.switch-btn.active + .switch-btn::before {
  display: none;
}

@media (max-width: 720px) {
  .workspace-mode-switch {
    justify-self: start;
    max-width: 100%;
    overflow-x: auto;
  }
}
</style>
