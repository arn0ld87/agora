<script setup>
defineProps({
  label: { type: String, default: '' },
  dark: { type: Boolean, default: false },
})
</script>

<template>
  <div class="card" :class="{ 'card--dark': dark }">
    <div v-if="label" class="card-label">{{ label }}</div>
    <slot />
  </div>
</template>

<style scoped>
.card {
  padding: var(--s-6);
  background: var(--paper-1);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  border-radius: var(--r-1);
}
.card--dark {
  background: var(--bg-dark);
  color: var(--fg-on-dark);
}
.card--dark .card-label { color: var(--fg-on-dark-muted); }
.card-label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
</style>
