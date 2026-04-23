<template>
  <div class="workspace-brand-link" @click="$emit('navigate-home')">
    <slot />
  </div>
</template>

<script setup>
defineEmits(['navigate-home'])
</script>

<style scoped>
.workspace-brand-link {
  font-family: var(--ff-serif);
  font-weight: 500;
  font-size: 22px;
  letter-spacing: -0.02em;
  cursor: pointer;
  color: var(--ink-0);
}

.workspace-brand-link:hover {
  color: var(--accent);
}
</style>
