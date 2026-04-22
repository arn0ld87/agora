<template>
  <div class="graph-legend">
    <span class="legend-title">Entity Types</span>
    <div class="legend-items">
      <div v-for="type in entityTypes" :key="type.name" class="legend-item">
        <span class="legend-dot" :style="{ background: type.color }"></span>
        <span class="legend-label">{{ type.name }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  entityTypes: {
    type: Array,
    default: () => [],
  },
})
</script>

<style scoped>
.graph-legend {
  position: absolute;
  bottom: var(--s-5);
  left: var(--s-5);
  background: var(--paper-0);
  padding: var(--s-3) var(--s-4);
  border-radius: var(--r-1);
  border: 1px solid var(--rule);
  z-index: 10;
}

.legend-title {
  display: block;
  font-family: var(--ff-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--accent);
  margin-bottom: var(--s-2);
  text-transform: uppercase;
  letter-spacing: var(--ls-mono);
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2) var(--s-4);
  max-width: 320px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--ff-mono);
  font-size: 11px;
  color: var(--fg-body);
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  white-space: nowrap;
}
</style>
