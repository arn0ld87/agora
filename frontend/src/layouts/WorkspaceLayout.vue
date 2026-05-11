<template>
  <div class="workspace-layout">
    <slot name="header" />
    <slot />
  </div>
</template>

<style scoped>
.workspace-layout {
  height: 100vh;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--surface-canvas, var(--bg-sunken));
  color: var(--text-primary, var(--fg));
  font-family: var(--font-sans, var(--ff-sans));
  overflow: hidden;
  isolation: isolate;
}
</style>
