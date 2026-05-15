<script setup lang="ts">
/**
 * QuickActionsRow — drei RouterLink-Tiles für Compare / History / Settings.
 * Workbench-These: ruhige Kacheln, Mono-Label, kein Akzent (Hero hat den Akzent).
 */
import { RouterLink } from 'vue-router'

interface Tile {
  to: string
  labelKey: string
  hintKey: string
}

const TILES: Tile[] = [
  { to: '/v4/compare/last', labelKey: 'dashboard.quick.compare', hintKey: 'dashboard.quick.compareHint' },
  { to: '/v4/history', labelKey: 'dashboard.quick.history', hintKey: 'dashboard.quick.historyHint' },
  { to: '/settings/general', labelKey: 'dashboard.quick.settings', hintKey: 'dashboard.quick.settingsHint' },
]
</script>

<template>
  <div class="qa-row">
    <RouterLink
      v-for="tile in TILES"
      :key="tile.to"
      :to="tile.to"
      class="qa-tile v4-state-selectable"
    >
      <span class="qa-tile__label">{{ $t(tile.labelKey) }}</span>
      <span class="qa-tile__hint">{{ $t(tile.hintKey) }}</span>
      <span class="qa-tile__arrow" aria-hidden="true">→</span>
    </RouterLink>
  </div>
</template>

<style scoped>
.qa-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.qa-tile {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  column-gap: 12px;
  padding: 16px 18px;
  /* v4-state-selectable liefert background/transition/cursor/hover/focus-ring */
  background: var(--surface-elevated, #fff);
  border-radius: var(--r-6, 12px);
  box-shadow: 0 0 0 1px var(--hairline);
  text-decoration: none;
  color: var(--text-primary);
  min-width: 0;
}

/* focus-visible: eigener Override da box-shadow-Fokus-Ring statt outline */
.qa-tile:focus-visible {
  outline: none;
  box-shadow: 0 0 0 1px var(--hairline), 0 0 0 3px var(--v4-state-focus-ring, var(--focus-ring));
}

.qa-tile__label {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  grid-row: 1;
  grid-column: 1;
}

.qa-tile__hint {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
  grid-row: 2;
  grid-column: 1;
  margin-top: 2px;
}

.qa-tile__arrow {
  grid-row: 1 / span 2;
  grid-column: 2;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 16px;
}

@media (max-width: 720px) {
  .qa-row {
    grid-template-columns: 1fr;
  }
}
</style>
