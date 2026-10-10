/**
 * Wirksame Persona-Schwelle eines Reports — Spiegel der Backend-Konstanten.
 *
 * Single Source of Truth im Backend:
 * `backend/app/services/report_agent/contract_constants.py::MIN_PERSONA_TABLE_ROWS`
 * (= 20). Der Report-Contract verlangt so viele Personas für die
 * DACH-Persona-Tabelle; `backend/app/services/prepare_service.py` deckelt die
 * Schwelle mit einem kleineren `max_agents`:
 * `persona_floor = min(MIN_PERSONA_TABLE_ROWS, max_agents)`. Genau diesen Wert
 * prüft das Report-Gate (`report_agent/workflow.py`) und seit UAT-001 auch die
 * Vorabprüfung beim Berichtstart (`report_generation.py`).
 *
 * Warum gespiegelt: Der Erstellungsdialog MUSS die Mindestzahl nennen (UAT-001 —
 * dort stand „10", während die wirksame Schwelle 20 war), und kein
 * Konfigurations-Endpunkt liefert sie aus. Bei einer Änderung im Backend ist
 * dieser Wert mitzuziehen; derselbe Spiegel existiert bereits für
 * {@link MIN_SIMULATION_AGENTS} (`report_agent/contract_constants.py`).
 */
export const MIN_PERSONA_TABLE_ROWS = 20

/**
 * Untergrenze der Personas-Obergrenze im Erstellungsdialog und in der
 * Vorbereitung — Spiegel von `MIN_SIMULATION_AGENTS`
 * (`backend/app/services/report_agent/contract_constants.py`).
 *
 * Eine Obergrenze von 10 ist bewusst zulässig: sie senkt den wirksamen Floor
 * auf 10 (`min(20, 10)`), nicht auf 0.
 */
export const MIN_SIMULATION_AGENTS = 10

/**
 * Effektive Report-Schwelle: `min(20, max(10, maxAgents))`, wie im Backend.
 *
 * `null`/`0` steht für „keine Obergrenze" (Backend: `max_agents` nicht gesetzt)
 * — dann gilt der Contract-Wert unverkürzt.
 */
export function effectivePersonaFloor(maxAgents: number | null | undefined): number {
  if (maxAgents === null || maxAgents === undefined || maxAgents <= 0) {
    return MIN_PERSONA_TABLE_ROWS
  }
  return Math.min(MIN_PERSONA_TABLE_ROWS, Math.max(MIN_SIMULATION_AGENTS, maxAgents))
}
