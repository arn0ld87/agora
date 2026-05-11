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
  grid-template-columns: minmax(160px, auto) 1fr minmax(240px, auto);
  align-items: center;
  min-height: 58px;
  gap: var(--sp-6, var(--s-5));
  padding: 0 var(--sp-6, var(--s-6));
  border-bottom: 1px solid var(--hairline, var(--rule));
  background: var(--surface-translucent, var(--bg-glass));
  color: var(--text-primary, var(--fg));
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  box-shadow: 0 1px 0 rgba(255,255,255,0.55);
  z-index: 10;
}

.workspace-brand {
  min-width: 0;
}

.workspace-center {
  justify-self: center;
  min-width: 0;
}

.workspace-status {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: var(--sp-3, var(--s-3));
  color: var(--text-secondary, var(--fg-muted));
}

.workspace-model-badge {
  max-width: min(260px, 28vw);
}

@media (max-width: 720px) {
  .workspace-header {
    grid-template-columns: 1fr;
    min-height: auto;
    gap: var(--sp-3, var(--s-3));
    padding: var(--sp-3, var(--s-3)) var(--sp-4, var(--s-4));
  }

  .workspace-center,
  .workspace-status {
    justify-self: start;
  }

  .workspace-status {
    flex-wrap: wrap;
  }
}
</style>
