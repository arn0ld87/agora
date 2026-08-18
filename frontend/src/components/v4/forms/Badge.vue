<script setup lang="ts">
withDefaults(defineProps<{
  tone?: 'green' | 'orange' | 'red' | 'purple' | 'teal' | 'blue' | 'gray'
  dot?: boolean
}>(), {
  tone: 'gray',
  dot: true,
})
</script>

<template>
  <span class="v4-badge" :class="`v4-badge--${tone}`">
    <span v-if="dot" class="v4-badge__dot" aria-hidden="true" />
    <slot />
  </span>
</template>

<style scoped>
.v4-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 8px;
  border-radius: var(--r-pill, 999px);
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  line-height: 1;
}

.v4-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
}

/* Tone-Varianten */
.v4-badge--gray {
  background: var(--gray-6);
  color: var(--text-secondary);
}

.v4-badge--green {
  background: var(--status-green-bg);
  color: var(--status-green);
}

.v4-badge--orange {
  background: var(--status-orange-bg);
  color: var(--status-orange);
}

.v4-badge--red {
  background: var(--status-red-bg);
  color: var(--status-red);
}

.v4-badge--purple {
  background: var(--status-purple-bg);
  color: var(--status-purple);
}

.v4-badge--teal {
  background: var(--status-teal-bg);
  color: var(--status-teal);
}

.v4-badge--blue {
  background: var(--accent-tint-bg);
  color: var(--accent);
}
</style>
