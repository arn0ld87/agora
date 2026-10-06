<template>
  <div class="shelf-layout" :data-testid="ShellTestId.root">
    <div class="shelf-layout__stack">
      <Stack :current="props.current" @select="(target) => emit('select', target)" />
    </div>

    <div class="shelf-layout__main">
      <div
        class="shelf-layout__panel shelf-layout__panel--shelf"
        :data-testid="ShellTestId.panelShelf"
        :data-hidden-narrow="hasSelection ? 'true' : 'false'"
      >
        <slot name="shelf" />
      </div>
      <div
        class="shelf-layout__panel shelf-layout__panel--dossier"
        :data-testid="ShellTestId.panelDossier"
        :data-hidden-narrow="hasSelection ? 'false' : 'true'"
      >
        <slot name="dossier" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ShellTestId } from '../../contracts/testIds'
import type { ShelfObject, ShelfObjectKind } from '../../types/shelf'
import Stack from './Stack.vue'

/**
 * ShelfLayout.vue — Inhaltsflaeche der Ablage (#1795, Ticket 5).
 *
 * Reiner Inhalt, keine Huelle: Stapel-Leiste oben, darunter zweispaltig
 * Shelf (Slot #shelf) und Dossier (Slot #dossier). Kopfzeile, Nutzermenue,
 * Aktivitaets-Indikator, Protokoll-Symbol, Suche und Undo-Toast liegen in
 * der einen Huelle (AppShell). Unter 1100px wird daraus eine Spalte: nur
 * eine der beiden Flaechen ist sichtbar, gesteuert ueber `current`
 * (Systemregel 09-systemregeln.html — kein Hamburger, keine Tab-Leiste,
 * der Stapel ist der Rueckweg).
 */

const props = defineProps<{
  current: ShelfObject | null
}>()

const emit = defineEmits<{
  select: [target: { kind: ShelfObjectKind; id: string } | null]
}>()

const hasSelection = computed(() => props.current !== null)
</script>

<style scoped>
.shelf-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--surface-base);
  color: var(--text-primary);
}

.shelf-layout__stack {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  min-height: 46px;
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--hairline);
}

.shelf-layout__main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr);
}

.shelf-layout__panel--shelf {
  border-right: 1px solid var(--hairline);
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.shelf-layout__panel--dossier {
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Unter 1100px: eine Spalte, die jeweils inaktive Flaeche wird ausgeblendet
   (Systemregel 09-systemregeln.html — kein Hamburger, keine Tab-Leiste). */
@media (max-width: 1099px) {
  .shelf-layout__main {
    grid-template-columns: 1fr;
  }
  .shelf-layout__panel[data-hidden-narrow='true'] {
    display: none;
  }
  .shelf-layout__panel--shelf {
    border-right: 0;
  }
}

@media (pointer: coarse) {
  .shelf-layout__stack {
    min-height: 56px;
  }
}

@media (max-width: 767px) {
  .shelf-layout__stack {
    padding-left: var(--sp-3);
    padding-right: var(--sp-3);
  }
}
</style>
