<script setup lang="ts">
/**
 * DropdownMenu — Wrapper über reka-ui DropdownMenuRoot/Trigger/Portal/Content.
 *
 * Slice FE-Redesign-1 · 2026-05-15
 *
 * Public API unverändert gegenüber Slice UI-G:
 *   <DropdownMenu align="end">
 *     <template #trigger="{ toggle, isOpen }">
 *       <Button @click="toggle">Aktionen</Button>
 *     </template>
 *     <template #default="{ close }">
 *       <DropdownMenuItem @select="close">Bearbeiten</DropdownMenuItem>
 *     </template>
 *   </DropdownMenu>
 *
 * Exposed: open/close/toggle/isOpen
 *
 * Was reka-ui jetzt liefert (gegen Eigenbau-Variante):
 * - aria-haspopup="menu" + aria-expanded auf DropdownMenuTrigger
 * - role="menu" + aria-orientation="vertical" auf Content
 * - Arrow-Up/Down navigiert zwischen Items
 * - Home/End zu erstem/letztem Item
 * - Type-Ahead-Suche
 * - Focus-Trap im offenen Menu
 * - Escape schließt Menu und gibt Fokus zurück
 * - Portal-aware Outside-Click-Detection (kein document-Listener mehr nötig)
 *
 * Portal-Hinweis: Panel wird via DropdownMenuPortal in document.body
 * gemountet. Tests müssen document.querySelector statt wrapper.find
 * für Panel-Elemente verwenden.
 */

import { ref } from 'vue'
import {
  DropdownMenuRoot,
  DropdownMenuTrigger,
  DropdownMenuPortal,
  DropdownMenuContent,
} from 'reka-ui'

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

function open(): void {
  isOpen.value = true
}

function close(): void {
  isOpen.value = false
}

function toggle(): void {
  isOpen.value = !isOpen.value
}

defineExpose({ open, close, toggle, isOpen })

defineSlots<{
  trigger: (props: { toggle: () => void; isOpen: boolean }) => unknown
  default: (props: { close: () => void }) => unknown
}>()
</script>

<template>
  <DropdownMenuRoot v-model:open="isOpen">
    <!-- as-child: reka-ui DropdownMenuTrigger merged seine ARIA-Attribute
         (aria-haspopup="menu", aria-expanded) direkt auf das erste Child-Element
         des trigger-Slots. Kein nested-button-Problem, weil kein eigenes <button>
         mehr gerendert wird — der Consumer-Button IM Slot übernimmt alle Attribute. -->
    <DropdownMenuTrigger as-child>
      <slot name="trigger" :toggle="toggle" :is-open="isOpen" />
    </DropdownMenuTrigger>

    <DropdownMenuPortal>
      <DropdownMenuContent
        class="dm-panel"
        :class="`dm-panel--align-${align}`"
        :align="align"
        :side-offset="6"
      >
        <slot :close="close" />
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>

<style scoped>
.dm-trigger {
  display: inline-block;
}

.dm-panel {
  min-width: 180px;
  padding: 4px;
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-3, 6px);
  box-shadow: var(--shadow-2);
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 1px;
  outline: none;
}

.dm-panel--align-start,
.dm-panel--align-end {
  /* Alignment wird von reka-ui über transform gesteuert.
     Klassen bleiben für visual-regression-snapshots und CSS-Overrides. */
}
</style>
