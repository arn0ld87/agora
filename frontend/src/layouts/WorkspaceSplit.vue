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

<script setup>
defineProps({
  leftStyle: {
    type: Object,
    default: () => ({}),
  },
  rightStyle: {
    type: Object,
    default: () => ({}),
  },
})
</script>

<style scoped>
.workspace-split {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.workspace-panel {
  height: 100%;
  overflow: hidden;
  transition: width 350ms cubic-bezier(0.2, 0.7, 0.2, 1), opacity 200ms ease;
}

.workspace-panel--left {
  border-right: 1px solid var(--rule);
}
</style>
