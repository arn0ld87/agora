/**
 * Run-Parameter-Query — Vertrag zwischen Step 2 (Sender) und Step 3 (Empfänger).
 *
 * Slice 5 · 2026-08-02 — Fix B-09/B-27 (Runden/Tage überlebten Schritt 2→3 nicht).
 *
 * Step 2 emittiert ``next-step`` mit den Werten, die der Nutzer gegen den
 * Auto-Vorschlag gesetzt hat. Der Wrapper verwarf sie bisher kommentarlos und
 * navigierte nur mit ``simulationId`` weiter; die Props ``maxRounds`` und
 * ``simulationDays`` an Step3Simulation blieben deshalb dauerhaft undefined.
 *
 * Warum Query und nicht der pendingUpload-Store: Step 3 ist eine eigene Route,
 * auf der eine laufende Simulation beobachtet wird. Ein Reload dort darf die
 * eingestellte Rundenzahl nicht verlieren. Der Store ist bloß ``reactive``,
 * nicht persistiert, und gehört fachlich dem Dashboard-Start (HeroNewRun).
 *
 * Diese Datei ist die einzige Stelle, an der die Query-Schlüssel definiert
 * werden — genau der implizite Schlüsseltausch zwischen zwei Seiten war die
 * Ursache des Bugs.
 */

export const MAX_ROUNDS_QUERY_KEY = 'maxRounds'
export const SIMULATION_DAYS_QUERY_KEY = 'simulationDays'

export interface RunParams {
  /** Vom Nutzer überstimmte Rundenzahl; ``null`` = Auto-Wert des Backends gilt. */
  maxRounds: number | null
  /** Vom Nutzer überstimmte Simulationstage; ``null`` = Auto-Wert des Backends gilt. */
  simulationDays: number | null
}

/** Query-Werte sind laut vue-router string, Array oder fehlend. */
export type QueryValue = string | (string | null)[] | null | undefined

/**
 * Normalisiert einen Wert auf eine positive Ganzzahl.
 *
 * Alles andere (0, negativ, Kommazahl, leer, NaN, Boolean, Mehrfach-Query)
 * gilt als "nicht gesetzt" und fällt auf ``null`` — ein unsinniger URL-Wert
 * darf nicht als Rundenzahl an das Backend gehen.
 */
export function coercePositiveInt(value: unknown): number | null {
  const raw = Array.isArray(value) ? value[0] : value

  if (typeof raw === 'number') {
    return Number.isInteger(raw) && raw > 0 ? raw : null
  }
  if (typeof raw !== 'string' || raw.trim() === '') {
    return null
  }
  const parsed = Number(raw)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

/** Liest die Run-Parameter aus einer Router-Query (Step-3-Seite). */
export function readRunParamsFromQuery(
  query: Record<string, QueryValue> | undefined | null,
): RunParams {
  return {
    maxRounds: coercePositiveInt(query?.[MAX_ROUNDS_QUERY_KEY]),
    simulationDays: coercePositiveInt(query?.[SIMULATION_DAYS_QUERY_KEY]),
  }
}

/**
 * Baut die Query-Fragmente für die Weiterleitung (Step-2-Seite).
 *
 * Nicht gesetzte Werte erzeugen keinen Schlüssel: fehlt der Parameter, gilt
 * bewusst der auto-generierte Wert, und dann gehört auch nichts in die URL.
 */
export function toRunParamsQuery(source: {
  maxRounds?: unknown
  simulationDays?: unknown
}): Record<string, string> {
  const query: Record<string, string> = {}

  const maxRounds = coercePositiveInt(source?.maxRounds)
  if (maxRounds !== null) {
    query[MAX_ROUNDS_QUERY_KEY] = String(maxRounds)
  }
  const simulationDays = coercePositiveInt(source?.simulationDays)
  if (simulationDays !== null) {
    query[SIMULATION_DAYS_QUERY_KEY] = String(simulationDays)
  }
  return query
}
