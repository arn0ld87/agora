import { ref } from 'vue'
import { createSimulationBranch } from '../api/simulation'

/**
 * Aus einem Bericht eine neue Simulation ableiten (Block B4).
 *
 * Der Nutzer hat es so gesagt: „es nutzt kaum sein Potential, mit den
 * erstellten Reports weiterzuarbeiten." Technisch gibt es den Weg
 * laengst — `POST /api/simulation/<id>/branch` legt eine Simulation an,
 * die die Personas des Vorlaufs uebernimmt. Er war nur im vierten
 * Schritt der alten Prozesskette vergraben und damit praktisch
 * unauffindbar.
 *
 * Abgeleitet wird immer MIT Personas (`copy_profiles: true`) und OHNE
 * die Berichtsartefakte: die Personen sollen dieselben sein, die
 * Auswertung eine neue.
 */

export interface DeriveResult {
  simulationId: string
}

export function useDeriveSimulation() {
  const busy = ref(false)
  const error = ref('')

  /**
   * @param sourceSimulationId Simulation, aus welcher der Bericht stammt
   * @param name Bezeichnung des neuen Laufs
   */
  async function derive(sourceSimulationId: string, name: string): Promise<DeriveResult | null> {
    if (!sourceSimulationId || !name.trim()) {
      error.value = 'missing_input'
      return null
    }
    busy.value = true
    error.value = ''
    try {
      const res = await createSimulationBranch(sourceSimulationId, {
        branch_name: name.trim(),
        copy_profiles: true,
        copy_report_artifacts: false,
      })
      const newId = res?.success ? res.data?.simulation_id : undefined
      if (!newId) {
        error.value = 'no_simulation_id'
        return null
      }
      return { simulationId: newId }
    } catch (err) {
      error.value = (err as Error).message
      return null
    } finally {
      busy.value = false
    }
  }

  return { busy, error, derive }
}
