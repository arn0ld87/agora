/**
 * „Personas fertig vorbereitet?" aus dem Arbeitsbereich des Laufs (#1801): die
 * Stufe `personas` steht auf einem Abschlusszustand (fertig, degradiert,
 * Fallback, unvollständig). Ohne Arbeitsbereich (z. B. in Einzeltests) gilt
 * `true`, weil dann keine Aussage möglich ist und nichts gesperrt werden soll.
 */
import { computed, inject, type ComputedRef } from 'vue'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'
import { DONE_KINDS } from '@/composables/run/runStageState'

export function usePersonasReady(): ComputedRef<boolean> {
  const ws = inject(RUN_WORKSPACE_KEY, null)
  return computed(() => {
    if (!ws) return true
    const row = ws.stages.value.find((s) => s.key === 'personas')
    return row !== undefined && DONE_KINDS.includes(row.state)
  })
}
