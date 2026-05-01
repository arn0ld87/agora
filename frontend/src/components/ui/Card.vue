<script setup>
defineProps({
  label: { type: String, default: '' },
  dark: { type: Boolean, default: false },
  glass: { type: Boolean, default: false },
})
</script>

<template>
  <div
    class="card"
    :class="{
      'card--dark': dark,
      'card--glass': glass,
    }"
  >
    <div v-if="label" class="card-label">{{ label }}</div>
    <slot />
  </div>
</template>

<style scoped>
.card {
  padding: var(--s-6);
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  border-radius: var(--r-3);
  box-shadow: var(--shadow-1);
}
.card--glass {
  background: var(--bg-glass);
  border-color: var(--rule-strong);
  backdrop-filter: blur(24px) saturate(160%);
  -webkit-backdrop-filter: blur(24px) saturate(160%);
  box-shadow: var(--shadow-glass);
}
.card--dark {
  background: var(--bg-inverse);
  color: var(--fg-on-inverse);
  border-color: color-mix(in oklch, var(--bg-inverse) 70%, transparent);
}
.card--dark .card-label { color: var(--fg-meta); }
.card-label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono-wide);
  text-transform: uppercase;
  color: var(--fg-muted);
  font-weight: 500;
}
</style>
