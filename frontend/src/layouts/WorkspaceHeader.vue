<script setup lang="ts">
import ThemeToggle from '../components/ui/ThemeToggle.vue'
import ActiveModelBadge from '../components/ActiveModelBadge.vue'
</script>

<template>
  <header class="workspace-header">
    <div class="workspace-brand">
      <slot name="brand" />
    </div>
    <div class="workspace-center">
      <slot name="center" />
    </div>
    <div class="workspace-status">
      <ActiveModelBadge class="workspace-model-badge" />
      <slot name="status" />
      <ThemeToggle class="workspace-theme-toggle" />
    </div>
  </header>
</template>

<style scoped>
.workspace-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--s-7);
  padding: var(--s-3) var(--s-6);
  border-bottom: 1px solid var(--rule);
  background: var(--bg-glass);
  backdrop-filter: blur(20px) saturate(160%);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
  z-index: 10;
}

.workspace-center {
  justify-self: center;
}

.workspace-status {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  gap: var(--s-3);
}

@media (max-width: 720px) {
  .workspace-header {
    grid-template-columns: 1fr;
    gap: var(--s-3);
  }

  .workspace-center,
  .workspace-status {
    justify-self: start;
  }
}
</style>
