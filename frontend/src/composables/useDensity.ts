/**
 * useDensity — Compact/Comfortable-Density-Toggle für App-Shell-Chrome.
 *
 * Slice FE-Redesign-6 · 2026-05-15
 *
 * Single-source-of-truth ist data-density auf document.documentElement.
 * CSS-Variablen-Overrides leben in tokens-v3.css ([data-density="compact"]).
 *
 * Persistence: localStorage key 'agora.density'.
 * FOUC-Schutz: applyOnMount() vor app.mount('#app') in main.ts aufrufen.
 */

import { ref } from 'vue'

export type Density = 'comfortable' | 'compact'

const STORAGE_KEY = 'agora.density'
const VALID: ReadonlyArray<Density> = ['comfortable', 'compact'] as const

function hydrate(): Density {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw !== null && VALID.includes(raw as Density)) return raw as Density
  } catch {
    // localStorage kann in bestimmten Kontexten gesperrt sein
  }
  return 'comfortable'
}

function applyToDom(value: Density): void {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-density', value)
  }
}

function persistToStorage(value: Density): void {
  try {
    localStorage.setItem(STORAGE_KEY, value)
  } catch {
    // Storage gesperrt — kein harter Fehler
  }
}

// Modul-globaler Singleton-State (einmalig initialisiert)
let _density = ref<Density>(hydrate())

export function useDensity() {
  function setDensity(value: Density): void {
    _density.value = value
    persistToStorage(value)
    applyToDom(value)
  }

  function toggle(): void {
    setDensity(_density.value === 'comfortable' ? 'compact' : 'comfortable')
  }

  function applyOnMount(): void {
    applyToDom(_density.value)
  }

  return {
    density: _density,
    setDensity,
    toggle,
    applyOnMount,
  }
}

/**
 * Nur für Tests: setzt den Singleton-State zurück, damit jeder Test
 * mit einem frischen useDensity-State startet.
 *
 * @internal — nicht in Produktions-Code aufrufen.
 */
useDensity._resetForTesting = function (): void {
  _density = ref<Density>(hydrate())
}
