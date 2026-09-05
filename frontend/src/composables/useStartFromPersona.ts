import { ref } from 'vue'
import { createSimulationFromPersonas } from '../api/simulation'

/**
 * Lauf aus einem Personasatz starten (Block B4, geteilt zwischen
 * Dossier.vue und Shelf.vue seit Redesign PR 3).
 *
 * Ein Personasatz ist nicht nur Archivgut: aus ihm laesst sich direkt
 * ein Lauf starten — ohne Dokument, ohne Graph. Vorher lag die Aktion
 * nur im Dossier-Kopf; die Ablage-Zeile selbst hatte fuer diese Sorte
 * gar keine Weiter-Aktion (Audit-Befund „Weiter-Aktion pro Kind").
 */

export interface StartFromPersonaResult {
  simulationId: string
}

export function useStartFromPersona() {
  const busy = ref(false)
  const error = ref('')

  /**
   * @param templateId Personasatz, mit dem der Lauf startet
   * @param name Bezeichnung des neuen Laufs
   */
  async function start(templateId: string, name: string): Promise<StartFromPersonaResult | null> {
    busy.value = true
    error.value = ''
    try {
      const res = await createSimulationFromPersonas({
        simulation_requirement: name,
        template_ids: [templateId],
      })
      const simId = res?.success ? res.data?.simulation_id : undefined
      if (!simId) {
        error.value = 'no_simulation_id'
        return null
      }
      return { simulationId: simId }
    } catch (err) {
      error.value = (err as Error).message
      return null
    } finally {
      busy.value = false
    }
  }

  return { busy, error, start }
}
