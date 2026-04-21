<script setup>
defineProps({
  variant: { type: String, default: 'outline' },
  dot: { type: Boolean, default: false },
})
</script>

<template>
  <span class="badge" :class="`badge--${variant}`">
    <span v-if="dot" class="dot" />
    <slot />
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  padding: 4px 10px;
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  line-height: 1.4;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  border-radius: var(--r-pill);
  border: 1px solid var(--rule-strong);
  color: var(--ink-1);
  background: transparent;
  white-space: nowrap;
}
.badge--solid { background: var(--ink-0); color: var(--paper-0); border-color: var(--ink-0); }
.badge--accent { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.badge--ghost { border-color: var(--rule); color: var(--fg-muted); }
.badge .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
</style>
