import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Ab dieser Breite abwaerts (inklusive) wird die Suche der Kopfleiste zum
 * Symbolknopf (Bauplan frontend-umbau, Abschnitt 11). Bewusst ein eigener
 * Wert neben MOBILE_BREAKPOINT_PX: der Mobil-Modus (< 768) tauscht die
 * ganze Huelle, hier schrumpft nur ein Knopf.
 */
export const COMPACT_TOOLBAR_MAX_PX = 1024
export const COMPACT_TOOLBAR_QUERY = `(max-width: ${COMPACT_TOOLBAR_MAX_PX}px)`

function currentMatch(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(COMPACT_TOOLBAR_QUERY).matches
}

/** Reaktiv: ist die Kopfleiste schmal genug fuer den Such-Symbolknopf. */
export function useCompactToolbar() {
  const compact = ref(currentMatch())
  let mql: MediaQueryList | null = null

  function update(e: MediaQueryListEvent): void {
    compact.value = e.matches
  }

  onMounted(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    mql = window.matchMedia(COMPACT_TOOLBAR_QUERY)
    compact.value = mql.matches
    mql.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    mql?.removeEventListener('change', update)
    mql = null
  })

  return { compact }
}
