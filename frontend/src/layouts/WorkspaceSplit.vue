<template>
  <main class="workspace-split">
    <section class="workspace-panel workspace-panel--left" :style="leftStyle">
      <slot name="left" />
    </section>
    <section class="workspace-panel workspace-panel--right" :style="rightStyle">
      <slot name="right" />
    </section>
  </main>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'

defineProps({
  leftStyle: {
    type: Object,
    default: (): CSSProperties => ({}),
  },
  rightStyle: {
    type: Object,
    default: (): CSSProperties => ({}),
  },
})
</script>

<style scoped>
.workspace-split {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 0;
  overflow: hidden;
  background: var(--surface-canvas, var(--bg-sunken));
}

.workspace-panel {
  height: 100%;
  min-width: 0;
  overflow: hidden;
  transition: width 320ms cubic-bezier(0.2, 0.7, 0.2, 1), opacity 180ms ease;
}

.workspace-panel--left {
  background: var(--surface-tint, var(--bg-panel));
  border-right: 1px solid var(--hairline, var(--rule));
  box-shadow: inset -1px 0 0 rgba(255,255,255,0.55);
}

.workspace-panel--right {
  background: var(--surface-canvas, var(--bg-sunken));
}

@media (max-width: 820px) {
  .workspace-split {
    flex-direction: column;
  }

  .workspace-panel {
    width: 100% !important;
    min-height: 0;
  }

  .workspace-panel--left {
    height: 42%;
    border-right: 0;
    border-bottom: 1px solid var(--hairline, var(--rule));
    box-shadow: inset 0 -1px 0 rgba(255,255,255,0.55);
  }

  .workspace-panel--right {
    height: 58%;
  }
}
</style>
