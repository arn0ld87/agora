/**
 * Lauf-Kennung der geöffneten Seite für die Konsole (Aktivität, #1797).
 *
 * In `/simulations/:simulationId/…` und in den alten Lauf-Ansichten
 * (`/v4/simulation/:simulationId`, `/simulation/:simulationId`) steht die
 * Simulationskennung im Param `simulationId`. Der Vergleich trägt sie nur als
 * Vorauswahl und zählt nicht als geöffneter Lauf. Ohne Router (Einzeltests)
 * bleibt der Wert `null`.
 */
import { computed, inject, type ComputedRef } from 'vue'
import { routeLocationKey } from 'vue-router'

export function useLogScope(): ComputedRef<string | null> {
  const route = inject(routeLocationKey, null)
  return computed(() => {
    if (!route) return null
    if (route.path.includes('/compare')) return null
    const id = route.params.simulationId
    return typeof id === 'string' && id ? id : null
  })
}
