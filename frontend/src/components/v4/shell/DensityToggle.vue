<script setup lang="ts">
/**
 * DensityToggle — Compact/Comfortable-Toggle für App-Shell-Topbar.
 *
 * Slice FE-Redesign-6 · 2026-05-15
 *
 * Nutzt useDensity-Composable als Single-Source-of-Truth.
 * Setzt data-density auf <html> + persistiert in localStorage.
 */
import { useDensity } from '@/composables/useDensity'

const { density, toggle } = useDensity()
</script>

<template>
  <button
    type="button"
    class="dt-root"
    :aria-pressed="density === 'compact'"
    :title="density === 'compact' ? 'Compact Mode aktiv' : 'Comfortable Mode aktiv'"
    @click="toggle"
  >
    <span class="dt-icon" aria-hidden="true">
      {{ density === 'compact' ? '▤' : '▦' }}
    </span>
    <span class="dt-label">
      {{ density === 'compact' ? 'Kompakt' : 'Komfort' }}
    </span>
  </button>
</template>

<style scoped>
.dt-root {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: transparent;
  border: 1px solid var(--hairline);
  border-radius: var(--r-2, 4px);
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 12px;
  cursor: pointer;
  transition: background 100ms ease, color 100ms ease;
}

.dt-root:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.dt-root[aria-pressed="true"] {
  background: var(--accent-tint-bg, var(--surface-hover));
  color: var(--accent, var(--text-primary));
}

.dt-root:focus-visible {
  outline: 2px solid var(--accent, currentColor);
  outline-offset: 2px;
}

.dt-icon {
  font-size: 14px;
  line-height: 1;
}
</style>
