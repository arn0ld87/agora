/**
 * useCancelAction — Abbrechen MIT 5-Sekunden-Rueckgaengig (Block B3).
 *
 * Festlegung Q22/14: KEIN Bestaetigungsdialog. cancel(runId) startet
 * stattdessen einen 5s-Timer und zeigt den Undo-Toast
 * (ShellTestId.undoToast/undoButton, aria-live="polite"). Laeuft der
 * Timer ab, ruft er cancelRun(runId) aus src/api/runs.ts auf. undo()
 * bricht den Timer ab, ohne die API zu rufen.
 *
 * pause()/resume() sind NICHT Teil des Undo-Flusses (Q21: Pause/Resume
 * gibt es nur fuer laufende Simulationen und wirkt sofort) — sie rufen
 * direkt pauseSimulation()/resumeSimulation() aus src/api/simulation.ts.
 *
 * Singleton-State (Modul-Scope, analog useCommandPalette): der Undo-
 * Toast ist EIN globales Element (in ShellRoot.vue gerendert), egal ob
 * "Abbrechen" aus einer Ablage-Zeile, dem Dossier-Kopf oder dem
 * Aktivitaets-Indikator ausgeloest wurde.
 */
import { ref } from 'vue'
import { cancelRun } from '../../api/runs'
import { pauseSimulation, resumeSimulation } from '../../api/simulation'

const UNDO_WINDOW_MS = 5000
const CONFIRM_DISPLAY_MS = 3000

export interface PendingCancel {
  runId: string
  /** Sekunden bis zum tatsaechlichen Abbruch, fuer den Countdown-Text. */
  secondsLeft: number
}

// Modul-Scope: ein Toast fuer die ganze Shell, unabhaengig vom Aufrufer.
const pending = ref<PendingCancel | null>(null)
/** Nach Ablauf des Undo-Fensters kurz die Bestaetigung zeigen (shelf.cancelRequested). */
const confirmed = ref<string | null>(null)

let timeoutId: ReturnType<typeof setTimeout> | null = null
let tickId: ReturnType<typeof setInterval> | null = null
let confirmTimeoutId: ReturnType<typeof setTimeout> | null = null

function clearTimer(): void {
  if (timeoutId) {
    clearTimeout(timeoutId)
    timeoutId = null
  }
  if (tickId) {
    clearInterval(tickId)
    tickId = null
  }
}

export function useCancelAction() {
  function cancel(runId: string): void {
    // Ein neuer Cancel ersetzt einen evtl. noch laufenden — es gibt nur
    // einen Toast; der vorherige Timer wird verworfen (kein API-Call fuer ihn).
    clearTimer()
    pending.value = { runId, secondsLeft: Math.ceil(UNDO_WINDOW_MS / 1000) }

    const startedAt = Date.now()
    tickId = setInterval(() => {
      if (!pending.value) return
      const elapsed = Date.now() - startedAt
      const left = Math.max(0, Math.ceil((UNDO_WINDOW_MS - elapsed) / 1000))
      pending.value = { runId, secondsLeft: left }
    }, 250)

    timeoutId = setTimeout(() => {
      clearTimer()
      pending.value = null
      void cancelRun(runId).then(() => {
        confirmed.value = runId
        if (confirmTimeoutId) clearTimeout(confirmTimeoutId)
        confirmTimeoutId = setTimeout(() => {
          confirmed.value = null
          confirmTimeoutId = null
        }, CONFIRM_DISPLAY_MS)
      })
    }, UNDO_WINDOW_MS)
  }

  function undo(): void {
    clearTimer()
    pending.value = null
  }

  async function pause(simulationId: string): Promise<void> {
    await pauseSimulation(simulationId)
  }

  async function resume(simulationId: string): Promise<void> {
    await resumeSimulation(simulationId)
  }

  return { pending, confirmed, cancel, undo, pause, resume }
}
