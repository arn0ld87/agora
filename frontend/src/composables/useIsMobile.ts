import { onBeforeUnmount, onMounted, ref } from 'vue'
import { MOBILE_MEDIA_QUERY } from '../constants/breakpoints'

/**
 * Reaktives „ist das ein schmales Geraet" (Block B4).
 *
 * Nutzt die vorhandene SSoT aus `constants/breakpoints.ts` statt eines
 * zweiten Breakpoints. Die neue Huelle braucht das nicht nur in CSS:
 * Der ⌘K-Knopf soll auf einem Telefon nicht bloss unsichtbar sein,
 * sondern gar nicht erst im Markup stehen — sonst bleibt er ein
 * Tab-Stop, der ins Leere fuehrt, und Screenreader lesen ein
 * Bedienelement vor, das dort niemand ausloesen kann.
 *
 * `matchMedia` fehlt in jsdom; ohne die Pruefung wuerde jeder
 * Komponententest beim Mounten werfen. Ohne matchMedia gilt „nicht
 * schmal" — die Desktop-Ansicht ist der sichere Rueckfall.
 */
function currentMatch(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(MOBILE_MEDIA_QUERY).matches
}

export function useIsMobile() {
  // Der Startwert wird SOFORT gelesen, nicht erst in onMounted: sonst
  // rendert der erste Durchlauf die Desktop-Fassung und korrigiert sich
  // einen Tick spaeter — auf dem Telefon ein sichtbares Zucken.
  const isMobile = ref(currentMatch())
  let mql: MediaQueryList | null = null

  function update(e: MediaQueryList | MediaQueryListEvent): void {
    isMobile.value = e.matches
  }

  onMounted(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    mql = window.matchMedia(MOBILE_MEDIA_QUERY)
    isMobile.value = mql.matches
    mql.addEventListener('change', update)
  })

  onBeforeUnmount(() => {
    mql?.removeEventListener('change', update)
    mql = null
  })

  return { isMobile }
}
