<script setup>
defineProps({
  size: { type: [Number, String], default: 22 },
  accent: { type: String, default: 'var(--accent)' },
  ink: { type: String, default: 'var(--fg)' },
  variant: { type: String, default: 'alpha-node' },
})
</script>

<template>
  <svg
    v-if="variant === 'alpha-node'"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    style="display:block"
    class="agora-glyph"
  >
    <path d="M3 5 L11 12 L3 19" :stroke="ink" stroke-width="1.5" stroke-linecap="square" />
    <path d="M21 5 L13 12 L21 19" :stroke="ink" stroke-width="1.5" stroke-linecap="square" />
    <circle cx="12" cy="12" r="3" :fill="accent" />
    <circle cx="12" cy="12" r="3" :stroke="accent" stroke-width="0.6" opacity="0.4" />
  </svg>

  <svg
    v-else-if="variant === 'cluster'"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    style="display:block"
    class="agora-glyph"
  >
    <line x1="6" y1="7" x2="18" y2="7" :stroke="ink" stroke-width="1.2" />
    <line x1="6" y1="7" x2="12" y2="18" :stroke="ink" stroke-width="1.2" />
    <line x1="18" y1="7" x2="12" y2="18" :stroke="ink" stroke-width="1.2" />
    <circle cx="6" cy="7" r="2.2" :fill="ink" />
    <circle cx="18" cy="7" r="2.2" :fill="ink" />
    <circle cx="12" cy="18" r="2.6" :fill="accent" />
  </svg>

  <svg
    v-else
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    style="display:block"
    class="agora-glyph"
  >
    <circle cx="12" cy="12" r="9" :stroke="ink" stroke-width="1" />
    <line x1="12" y1="2" x2="12" y2="22" :stroke="ink" stroke-width="1" />
    <line x1="2" y1="12" x2="22" y2="12" :stroke="ink" stroke-width="1" />
    <circle cx="12" cy="12" r="2.4" :fill="accent" />
  </svg>
</template>
