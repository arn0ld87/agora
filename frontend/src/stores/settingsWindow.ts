import { ref } from 'vue'
import { defineStore } from 'pinia'

/**
 * Merkt sich die Ansicht unter dem Einstellungsfenster (Bauplan §5).
 *
 * Das Fenster ist eine eigene Adresse (`/settings/:section`), liegt aber über
 * der zuletzt gezeigten Ansicht. Der Router setzt `returnTo` beim Öffnen aus
 * der App (`fullPath` der Ansicht davor) und leert ihn beim Verlassen.
 * `null` heißt: Direktaufruf (neuer Tab) — die Bibliothek der Läufe dient als
 * Hintergrund und als Ziel von „Schließen“.
 */
export const useSettingsWindowStore = defineStore('settingsWindow', () => {
  const returnTo = ref<string | null>(null)

  function open(previous: string | null): void {
    returnTo.value = previous
  }

  function reset(): void {
    returnTo.value = null
  }

  return { returnTo, open, reset }
})
