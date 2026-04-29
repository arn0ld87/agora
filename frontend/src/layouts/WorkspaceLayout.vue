<template>
  <div class="workspace-layout">
    <slot name="header" />
    <slot />
  </div>
</template>

<style scoped>
.workspace-layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  overflow: hidden;
}
</style>
