<template>
  <!-- Undo-Toast (Q22/14): global, egal ob Abbrechen aus Ablage-Zeile,
       Dossier-Kopf oder Aktivitaets-Indikator ausgeloest wurde. -->
  <div
    v-if="cancelAction.pending.value || cancelAction.confirmed.value"
    class="undo-toast"
    role="status"
    aria-live="polite"
    :data-testid="ShellTestId.undoToast"
  >
    <template v-if="cancelAction.pending.value">
      <span>{{ t('shelf.undoHint', { s: cancelAction.pending.value.secondsLeft }) }}</span>
      <button type="button" class="undo-toast__btn" :data-testid="ShellTestId.undoButton" @click="cancelAction.undo()">
        {{ t('shelf.undo') }}
      </button>
    </template>
    <template v-else>
      <span>{{ t('shelf.cancelRequested') }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ShellTestId } from '../../contracts/testIds'
import { useCancelAction } from './useCancelAction'

/**
 * UndoToast.vue — der EINE globale Undo-Toast fuer „Abbrechen“ (#1795,
 * Ticket 5). Frueher in ShellRoot.vue gerendert, jetzt einmal in der Huelle
 * (AppShell). useCancelAction ist ein Singleton, der Toast zeigt dessen
 * Zustand unabhaengig vom Ausloeser.
 */

const { t } = useI18n()
const cancelAction = useCancelAction()
</script>

<style scoped>
.undo-toast {
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

.undo-toast__btn {
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

.undo-toast__btn:hover {
  background: var(--accent-tint-bg);
}

.undo-toast__btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@media (max-width: 767px) {
  .undo-toast {
    left: var(--sp-3);
    right: var(--sp-3);
    transform: none;
    justify-content: space-between;
  }
}

@media (prefers-reduced-motion: reduce) {
  .undo-toast__btn {
    transition: none;
  }
}
</style>
