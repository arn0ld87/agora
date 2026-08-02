/**
 * Run-Registry-ID und Simulation-ID — getrennte Branded Types.
 *
 * Issue #1023 (Slice 5, Regression aus PR #997): `?runId=` transportierte
 * zwei fachlich unvereinbare Werte. `reportRoute.ts` dokumentiert `runId`
 * ausdrücklich als Registry-UUID für `/api/runs/<id>`
 * (`backend/app/services/run_registry.py::f"run_{uuid.uuid4().hex[:12]}"`).
 * `StepInteractionView.vue` las denselben Query-Parameter aber und reichte
 * ihn als `simulation_id` durch (`sim_{uuid.hex[:12]}`,
 * `backend/app/services/simulation_manager.py`). Trifft eine echte
 * `run_…`-ID auf den Interaktions-Pfad, scheitert jede Chat-/Interview-
 * Anfrage mit "Invalid simulation_id format".
 *
 * Diese Datei ist die einzige Stelle, die die Präfix-Konvention beider
 * ID-Räume kennt. Neue Konsumenten prüfen hier, statt eine eigene
 * Heuristik zu pflegen.
 */

/** Registry-eindeutige Run-ID, z. B. für `/api/runs/<id>` (`run_…`). */
export type RunRegistryId = string & { readonly __brand: 'RunRegistryId' }

/** Simulation-ID, z. B. für `/api/simulation/<id>/chat` (`sim_…`). */
export type SimulationId = string & { readonly __brand: 'SimulationId' }

const RUN_REGISTRY_ID_PREFIX = 'run_'
const SIMULATION_ID_PREFIX = 'sim_'

export function isRunRegistryId(value: unknown): value is RunRegistryId {
  return typeof value === 'string' && value.startsWith(RUN_REGISTRY_ID_PREFIX)
}

export function isSimulationId(value: unknown): value is SimulationId {
  return typeof value === 'string' && value.startsWith(SIMULATION_ID_PREFIX)
}

/**
 * Gibt den Wert nur zurück, wenn er wie eine Simulation-ID aussieht.
 *
 * Eine `run_…`-ID (oder jeder andere Nicht-`sim_`-Wert) wird verworfen,
 * statt sie ungeprüft als `simulation_id` weiterzureichen — genau der
 * Defekt aus Issue #1023.
 */
export function asSimulationId(value: unknown): SimulationId | null {
  return isSimulationId(value) ? value : null
}
