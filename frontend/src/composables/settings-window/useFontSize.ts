/**
 * useFontSize — Schriftgröße der Oberfläche in drei Stufen (#1799, Etappe 3).
 *
 * Single-source-of-truth ist `data-font-size` auf document.documentElement;
 * die Werte je Stufe stehen in assets/styles/font-scale.css (überschreibt die
 * semantischen --fs-*-Token). 'normal' entspricht dem bisherigen Zustand.
 *
 * Persistence: localStorage key 'agora.fontSize' (Zugriff in try/catch), wie
 * useTheme und useDensity. main.ts ruft applyOnMount() vor app.mount().
 */
import { readonly, ref, type Ref } from 'vue'

export type FontSize = 'small' | 'normal' | 'large'

export const FONT_SIZE_STORAGE_KEY = 'agora.fontSize'
export const FONT_SIZES: ReadonlyArray<FontSize> = ['small', 'normal', 'large']

function hydrate(): FontSize {
  try {
    const raw = localStorage.getItem(FONT_SIZE_STORAGE_KEY)
    if (raw !== null && FONT_SIZES.includes(raw as FontSize)) return raw as FontSize
  } catch {
    // localStorage kann in bestimmten Kontexten gesperrt sein
  }
  return 'normal'
}

function applyToDom(value: FontSize): void {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-font-size', value)
  }
}

function persist(value: FontSize): void {
  try {
    localStorage.setItem(FONT_SIZE_STORAGE_KEY, value)
  } catch {
    // Storage gesperrt — kein harter Fehler
  }
}

let current = ref<FontSize>(hydrate())

export function useFontSize(): {
  fontSize: Readonly<Ref<FontSize>>
  setFontSize: (value: FontSize) => void
  applyOnMount: () => void
} {
  function setFontSize(value: FontSize): void {
    if (!FONT_SIZES.includes(value)) return
    current.value = value
    persist(value)
    applyToDom(value)
  }

  return {
    fontSize: readonly(current),
    setFontSize,
    applyOnMount: () => applyToDom(current.value),
  }
}

/** @internal — nur für Tests: liest den Speicher neu. */
useFontSize._resetForTesting = function (): void {
  current = ref<FontSize>(hydrate())
}
