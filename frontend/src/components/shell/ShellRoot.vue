<template>
  <div class="shell-root" :data-testid="ShellTestId.root">
    <header class="shell-root__topbar">
      <div class="shell-root__brand">
        <span class="shell-root__brand-dot" aria-hidden="true"></span>
        <span class="shell-root__brand-name">{{ t('brand.name') }}</span>
      </div>
      <span class="shell-root__divider" aria-hidden="true"></span>

      <Stack :current="props.current" @select="(target) => emit('select', target)" />

      <span class="shell-root__spacer"></span>

      <ActivityIndicator :objects="props.activeObjects" @select="(target) => emit('select', target)" />

      <!-- Auf dem Telefon gibt es keine Tastenkombination auszuloesen.
           Der Knopf verschwindet deshalb aus dem Markup, statt nur
           unsichtbar zu sein — sonst bliebe er ein Tab-Stop ins Leere. -->
      <button
        v-if="!isMobile"
        type="button"
        class="shell-root__cmdk"
        :data-testid="ShellTestId.cmdkTrigger"
        :aria-label="t('cmd.trigger')"
        :title="t('cmd.trigger')"
        @click="openPalette"
      >
        &#8984;K
      </button>

      <div class="shell-root__user">
        <UserMenu />
      </div>
    </header>

    <main class="shell-root__main">
      <div
        class="shell-root__panel shell-root__panel--shelf"
        :data-testid="ShellTestId.panelShelf"
        :data-hidden-narrow="hasSelection ? 'true' : 'false'"
      >
        <slot name="shelf" />
      </div>
      <div
        class="shell-root__panel shell-root__panel--dossier"
        :data-testid="ShellTestId.panelDossier"
        :data-hidden-narrow="hasSelection ? 'false' : 'true'"
      >
        <slot name="dossier" />
      </div>
    </main>

    <!-- Undo-Toast (Q22/14): global, egal ob Abbrechen aus Ablage-Zeile,
         Dossier-Kopf oder Aktivitaets-Indikator ausgeloest wurde. -->
    <div
      v-if="cancelAction.pending.value || cancelAction.confirmed.value"
      class="shell-root__toast"
      role="status"
      aria-live="polite"
      :data-testid="ShellTestId.undoToast"
    >
      <template v-if="cancelAction.pending.value">
        <span>{{ t('shelf.undoHint', { s: cancelAction.pending.value.secondsLeft }) }}</span>
        <button type="button" class="shell-root__toast-btn" :data-testid="ShellTestId.undoButton" @click="cancelAction.undo()">
          {{ t('shelf.undo') }}
        </button>
      </template>
      <template v-else>
        <span>{{ t('shelf.cancelRequested') }}</span>
      </template>
    </div>

    <!-- Command-Palette: lazy gemountet, analog AppShell.vue (Slice v4-shell). -->
    <CommandPalette v-if="wasPaletteOpened" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShellTestId } from '../../contracts/testIds'
import UserMenu from './UserMenu.vue'
import { useIsMobile } from '../../composables/useIsMobile'
import type { ShelfObject, ShelfObjectKind } from '../../types/shelf'
import { useCommandPalette } from '../../composables/useCommandPalette'
import Stack from './Stack.vue'
import ActivityIndicator from './ActivityIndicator.vue'
import { useCancelAction } from './useCancelAction'

/**
 * ShellRoot.vue — Grundgeruest der Neuhuelle „Richtung B · Dossier“
 * (Block B3).
 *
 * Schmale Kopfzeile + darunter zweispaltig Shelf (Slot #shelf) und
 * Dossier (Slot #dossier). Unter 1100px wird daraus eine Spalte: nur
 * eine der beiden Flaechen ist sichtbar, gesteuert ueber `current`
 * (Systemregel 09-systemregeln.html — kein Hamburger, keine Tab-
 * Leiste, der Stapel ist der Rueckweg).
 *
 * Abweichung von 01-ablage.html: die Kopfzeile der Vorlage zeigt
 * zusaetzlich Neo4j/Redis/MiniMax-Statuspunkte. Der Auftrag zaehlt
 * die Kopfzeilen-Elemente explizit auf (Wortmarke, Stapel, ⌘K-Hinweis,
 * Aktivitaets-Indikator, Nutzermenue-Platzhalter) — Systemstatus ist
 * nicht darunter, und useSystemStatus anzubinden waere eine zweite,
 * hier nicht beauftragte Datenquelle. Siehe Bericht.
 */

const props = defineProps<{
  current: ShelfObject | null
  activeObjects: ShelfObject[]
}>()

const emit = defineEmits<{
  select: [target: { kind: ShelfObjectKind; id: string } | null]
}>()

const { t } = useI18n()
const cancelAction = useCancelAction()
const { isMobile } = useIsMobile()
const { isOpen: isPaletteOpen, open: openPalette } = useCommandPalette()
const wasPaletteOpened = ref(false)

const CommandPalette = defineAsyncComponent(() => import('../v4/shell/CommandPalette.vue'))

const hasSelection = computed(() => props.current !== null)

watch(
  isPaletteOpen,
  (open) => {
    if (open) wasPaletteOpened.value = true
  },
  { immediate: true },
)

function onKeyDown(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    openPalette()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))
</script>

<style scoped>
.shell-root {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--surface-base);
  color: var(--text-primary);
}

.shell-root__topbar {
  /* 46px ist ein Maus-Mass. Auf Touch waechst die Leiste mit, sonst
     stehen 44px-Ziele in einer 46px-Zeile ohne Luft. */
  height: 46px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--hairline);
}

.shell-root__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.shell-root__brand-dot {
  width: 13px;
  height: 13px;
  border: 1.5px solid var(--accent);
  border-radius: 50%;
}

.shell-root__brand-name {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.shell-root__divider {
  width: 1px;
  height: 18px;
  background: var(--hairline);
  flex-shrink: 0;
}

.shell-root__spacer {
  flex: 1;
}

.shell-root__cmdk {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-tertiary);
  border: 1px solid var(--hairline);
  border-radius: 3px;
  padding: 2px 8px;
  background: transparent;
  cursor: pointer;
  flex-shrink: 0;
}

.shell-root__cmdk:hover {
  color: var(--text-primary);
  border-color: var(--hairline-strong);
}

.shell-root__cmdk:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.shell-root__main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr);
}

.shell-root__panel--shelf {
  border-right: 1px solid var(--hairline);
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.shell-root__panel--dossier {
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.shell-root__toast {
  position: fixed;
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  z-index: 80;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--surface-elevated);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--r-5);
  box-shadow: var(--shadow-3);
  font-size: var(--fs-callout);
  color: var(--text-primary);
}

.shell-root__toast-btn {
  height: 26px;
  padding: 0 10px;
  border-radius: var(--r-3);
  border: 1px solid var(--accent);
  background: transparent;
  color: var(--accent);
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.shell-root__toast-btn:hover {
  background: var(--accent-tint-bg);
}

.shell-root__toast-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* Unter 1100px: eine Spalte, die jeweils inaktive Flaeche wird ausgeblendet
   (Systemregel 09-systemregeln.html — kein Hamburger, keine Tab-Leiste). */
@media (max-width: 1099px) {
  .shell-root__main {
    grid-template-columns: 1fr;
  }
  .shell-root__panel[data-hidden-narrow='true'] {
    display: none;
  }
  .shell-root__panel--shelf {
    border-right: 0;
  }
}

@media (pointer: coarse) {
  .shell-root__topbar {
    height: 56px;
  }
}

/* Telefon (< 768px, SSoT constants/breakpoints.ts): die Kopfzeile
   traegt nur noch, was dort auch etwas tut. Die Wortmarke schrumpft auf
   ihren Punkt — der Name kostet Platz, den Stapel und Aktivitaet
   dringender brauchen; der ⌘K-Knopf ist bereits aus dem Markup. */
@media (max-width: 767px) {
  .shell-root__topbar {
    padding-left: var(--sp-3);
    padding-right: var(--sp-3);
    gap: var(--sp-2);
  }
  .shell-root__brand-name,
  .shell-root__divider {
    display: none;
  }
  .shell-root__toast {
    left: var(--sp-3);
    right: var(--sp-3);
    transform: none;
    justify-content: space-between;
  }
}

@media (prefers-reduced-motion: reduce) {
  .shell-root__cmdk,
  .shell-root__toast-btn {
    transition: none;
  }
}
</style>
