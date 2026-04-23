<template>
  <header class="workspace-header">
    <div class="workspace-brand">
      <slot name="brand" />
    </div>
    <div class="workspace-center">
      <slot name="center" />
    </div>
    <div class="workspace-status">
      <slot name="status" />
    </div>
  </header>
</template>

<style scoped>
.workspace-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--s-7);
  padding: var(--s-4) var(--s-6);
  border-bottom: 1px solid var(--rule-strong);
  background: var(--paper-0);
  z-index: 10;
}

.workspace-center {
  justify-self: center;
}

.workspace-status {
  justify-self: end;
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
