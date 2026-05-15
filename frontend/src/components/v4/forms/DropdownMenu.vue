<script setup lang="ts">
/**
 * DropdownMenu — einfaches Click-Outside-Dropdown für Agora Design v4
 * Slice UI-G · 2026-05-15
 *
 * Use-Case: Aktions-Menüs in DataTable-Zeilen, Topbar-User-Menü, Run-Card-Aktionen.
 *
 * API:
 *   <DropdownMenu>
 *     <template #trigger="{ toggle, isOpen }">
 *       <Button :aria-expanded="isOpen" @click="toggle">Aktionen</Button>
 *     </template>
 *     <template #default="{ close }">
 *       <DropdownMenuItem @select="() => { onEdit(); close() }">Bearbeiten</DropdownMenuItem>
 *       <DropdownMenuItem variant="danger" @select="() => { onDelete(); close() }">Löschen</DropdownMenuItem>
 *     </template>
 *   </DropdownMenu>
 *
 * Hinweis: Slot-Props (`close`) sind nur via `<template #default="{ close }">`
 * zugänglich, nicht über lose Default-Slot-Children.
 *
 * Keyboard:
 * - ESC schließt das Menü und gibt Fokus an Trigger zurück.
 * - Click outside schließt das Menü.
 *
 * Listener-Lifecycle: document-level click/keydown werden NUR während offener
 * Phase registriert — vermeidet O(N)-globale-Listener bei vielen Dropdowns
 * (z. B. eine pro DataTable-Zeile).
 *
 * Wir verwenden bewusst kein @floating-ui / Reka-UI:
 * - Use-Cases sind alle „Trigger-rechts, Menü-darunter-rechts-aligned" — keine
 *   Collision-Detection nötig.
 * - Halte Dependencies minimal (siehe shadcn-vue-evaluation.md).
 */

import { onBeforeUnmount, ref, watch } from 'vue'

withDefaults(
  defineProps<{
    /** Alignment des Panels relativ zum Trigger */
    align?: 'start' | 'end'
  }>(),
  {
    align: 'end',
  },
)

const isOpen = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const triggerWrapperRef = ref<HTMLElement | null>(null)

function open(): void {
  isOpen.value = true
}

function close(): void {
  isOpen.value = false
}

function toggle(): void {
  isOpen.value = !isOpen.value
}

function onDocumentClick(event: MouseEvent): void {
  if (!isOpen.value) return
  const target = event.target as Node | null
  if (!target) return
  if (rootRef.value && !rootRef.value.contains(target)) {
    close()
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && isOpen.value) {
    close()
    // Fokus zurück auf erste fokussierbare Element im Trigger
    const trigger = triggerWrapperRef.value?.querySelector<HTMLElement>(
      'button, [tabindex]:not([tabindex="-1"])',
    )
    trigger?.focus()
  }
}

function attachGlobalListeners(): void {
  document.addEventListener('click', onDocumentClick, true)
  document.addEventListener('keydown', onKeydown)
}

function detachGlobalListeners(): void {
  document.removeEventListener('click', onDocumentClick, true)
  document.removeEventListener('keydown', onKeydown)
}

// Listener nur während offener Phase — skaliert auch bei Dropdown-pro-Tabellenzeile.
watch(isOpen, (open) => {
  if (open) attachGlobalListeners()
  else detachGlobalListeners()
})

onBeforeUnmount(() => {
  detachGlobalListeners()
})

defineExpose({ open, close, toggle, isOpen })

defineSlots<{
  trigger: (props: { toggle: () => void; isOpen: boolean }) => unknown
  default: (props: { close: () => void }) => unknown
}>()
</script>

<template>
  <div ref="rootRef" class="dm-root">
    <div ref="triggerWrapperRef" class="dm-trigger">
      <slot name="trigger" :toggle="toggle" :is-open="isOpen" />
    </div>

    <div
      v-if="isOpen"
      class="dm-panel"
      :class="`dm-panel--align-${align}`"
      role="menu"
    >
      <slot :close="close" />
    </div>
  </div>
</template>

<style scoped>
.dm-root {
  position: relative;
  display: inline-block;
}

.dm-panel {
  position: absolute;
  top: calc(100% + 6px);
  min-width: 180px;
  padding: 4px;
  background: var(--surface-elevated, #fff);
  border: 1px solid var(--hairline);
  border-radius: var(--r-3, 6px);
  box-shadow: var(--shadow-2, 0 8px 24px rgba(0, 0, 0, 0.12));
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.dm-panel--align-start {
  left: 0;
}

.dm-panel--align-end {
  right: 0;
}
</style>
