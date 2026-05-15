<script setup lang="ts">
/**
 * DropdownMenuItem — Einzeleintrag für DropdownMenu
 * Slice UI-G · 2026-05-15
 *
 * Emit `select` löst die Aktion aus. Konsument bekommt zusätzlich Zugriff
 * auf `close` über den DropdownMenu-Slot-Prop, um das Menü nach Klick zu
 * schließen.
 */

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
  select: [event: MouseEvent]
}>()

function onClick(event: MouseEvent): void {
  if (event.defaultPrevented) return
  emit('select', event)
}
</script>

<template>
  <button
    type="button"
    class="dmi-root"
    :class="[`dmi-root--${variant}`, { 'dmi-root--disabled': disabled }]"
    role="menuitem"
    :disabled="disabled"
    @click="onClick"
  >
    <slot />
  </button>
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
  transition: background 80ms ease;
}

.dmi-root:hover:not(:disabled),
.dmi-root:focus-visible:not(:disabled) {
  background: var(--surface-hover);
  outline: none;
}

.dmi-root--danger {
  color: var(--status-red);
}

.dmi-root--danger:hover:not(:disabled),
.dmi-root--danger:focus-visible:not(:disabled) {
  background: var(--status-red-bg);
}

.dmi-root--disabled,
.dmi-root:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
