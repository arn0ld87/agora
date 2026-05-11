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
  padding: var(--sp-6, var(--s-6));
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline, var(--rule));
  display: flex;
  flex-direction: column;
  gap: var(--sp-4, var(--s-4));
  border-radius: var(--r-7, var(--r-3));
  box-shadow: var(--shadow-1);
}
.card--glass {
  background: var(--surface-translucent, var(--bg-glass));
  border-color: rgba(255,255,255,0.6);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  box-shadow: var(--shadow-2, var(--shadow-glass));
}
.card--dark {
  background: var(--text-primary, var(--bg-inverse));
  color: var(--surface-base, var(--fg-on-inverse));
  border-color: var(--text-primary, var(--bg-inverse));
}
.card--dark .card-label { color: rgba(255,255,255,0.66); }
.card-label {
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-caption-1, 11px);
  letter-spacing: 0;
  text-transform: none;
  color: var(--text-secondary, var(--fg-muted));
  font-weight: 600;
}
</style>
