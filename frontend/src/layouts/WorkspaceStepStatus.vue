<template>
  <div class="workspace-step-status">
    <span class="kicker-row">
      <span class="step-counter">{{ stepCounter }}</span>
      <span class="step-name">{{ stepName }}</span>
    </span>
    <span class="status-tag" :class="`status-${statusKind}`">
      <span class="status-dot" :class="`status-dot--${statusKind}`" />
      {{ statusText }}
    </span>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  stepCounter: {
    type: String,
    required: true,
  },
  stepName: {
    type: String,
    required: true,
  },
  statusKind: {
    type: String,
    required: true,
  },
  statusText: {
    type: String,
    required: true,
  },
})
</script>

<style scoped>
.workspace-step-status {
  display: inline-flex;
  align-items: center;
  gap: var(--s-5);
}

.kicker-row {
  display: inline-flex;
  align-items: baseline;
  gap: var(--s-3);
}

.step-counter {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.step-name {
  font-family: var(--ff-serif);
  font-size: var(--fs-20);
  color: var(--ink-0);
}

.status-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.status-tag.status-error {
  color: #b00020;
}

.status-tag.status-done {
  color: var(--ink-0);
}

.status-tag.status-running {
  color: var(--accent);
}

.status-tag.status-paused {
  color: var(--ink-3);
}
</style>
