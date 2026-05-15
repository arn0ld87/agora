<script setup lang="ts">
/**
 * DropdownMenuItem — Wrapper über reka-ui DropdownMenuItem.
 *
 * Slice FE-Redesign-1 · 2026-05-15
 *
 * Public API unverändert: emit `select`, props `variant`/`disabled`.
 * reka-ui übernimmt ARIA-Rolle (role="menuitem"), aria-disabled,
 * data-disabled, data-highlighted, Keyboard-Handling (Arrow, Home/End,
 * Type-Ahead) und Focus-Management automatisch.
 *
 * Abweichung von HTML-Semantik: reka-ui setzt aria-disabled="true"
 * statt HTML disabled-Attribut — das ist ARIA-konform und verhindert
 * Tab-Index-Konflikte im Focus-Trap.
 */

import { DropdownMenuItem } from 'reka-ui'

withDefaults(
  defineProps<{
    variant?: 'default' | 'danger'
    disabled?: boolean
  }>(),
  {
    variant: 'default',
    disabled: false,
  },
)

const emit = defineEmits<{
  select: [event: Event]
}>()

function onSelect(event: Event): void {
  if (event.defaultPrevented) return
  emit('select', event)
}
</script>

<template>
  <DropdownMenuItem
    class="dmi-root v4-state-selectable"
    :class="[`dmi-root--${variant}`, { 'dmi-root--disabled': disabled }]"
    :disabled="disabled"
    @select="onSelect"
  >
    <slot />
  </DropdownMenuItem>
</template>

<style scoped>
.dmi-root {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  font-size: 13px;
  font-family: var(--font-sans);
  color: var(--text-primary);
  background: transparent;
  border: 0;
  border-radius: var(--r-2, 4px);
  cursor: pointer;
  text-align: left;
  /* transition + outline-none: via .v4-state-selectable */
}

/* reka-ui setzt data-highlighted — v4-state-selectable deckt :hover + data-highlighted ab.
   Hartkodierte Werte entfernt; Overrides via Tokens. */

.dmi-root--danger {
  color: var(--status-red);
}

/* Danger-Variante: BG-Override für Hover + Keyboard-Highlight */
.dmi-root--danger:hover:not([data-disabled]),
.dmi-root--danger[data-highlighted]:not([data-disabled]) {
  background: var(--status-red-bg);
}

/* Disabled: .v4-state-selectable hat kein Disabled-Styling, hier explizit */
.dmi-root--disabled,
.dmi-root[data-disabled] {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
}
</style>
