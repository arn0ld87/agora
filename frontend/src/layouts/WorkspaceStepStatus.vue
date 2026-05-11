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
  min-width: 0;
  gap: var(--sp-4, var(--s-4));
}

.kicker-row {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: var(--sp-2, var(--s-2));
}

.step-counter {
  font-family: var(--font-mono, var(--ff-mono));
  font-feature-settings: "tnum","zero";
  font-size: var(--fs-caption-1, var(--fs-11));
  line-height: 1;
  letter-spacing: 0;
  color: var(--text-tertiary, var(--fg-muted));
  white-space: nowrap;
}

.step-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-headline, var(--fs-18));
  line-height: var(--lh-headline, 1.25);
  font-weight: 590;
  letter-spacing: 0;
  color: var(--text-primary, var(--fg));
}

.status-tag {
  display: inline-flex;
  align-items: center;
  flex: none;
  gap: var(--sp-2, var(--s-2));
  min-height: 22px;
  padding: 0 9px;
  border-radius: var(--r-pill);
  background: var(--status-gray-bg, var(--bg-elevated));
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-caption-1, var(--fs-11));
  line-height: 1;
  font-weight: 590;
  letter-spacing: 0;
  color: var(--status-gray, var(--fg-muted));
  box-shadow: inset 0 0 0 1px rgba(0,0,0,0.04);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.status-tag.status-error {
  background: var(--status-red-bg, var(--err-soft));
  color: var(--status-red, var(--status-error));
}

.status-tag.status-done {
  background: var(--status-green-bg, var(--ok-soft));
  color: var(--status-green, var(--status-success));
}

.status-tag.status-running {
  background: var(--accent-tint-bg, var(--accent-soft));
  color: var(--accent);
}

.status-tag.status-paused {
  background: var(--status-orange-bg, var(--warn-soft));
  color: var(--status-orange, var(--warn));
}

@media (max-width: 720px) {
  .workspace-step-status {
    width: 100%;
    flex-wrap: wrap;
    gap: var(--sp-3, var(--s-3));
  }

  .kicker-row {
    flex: 1 1 220px;
  }
}
</style>
