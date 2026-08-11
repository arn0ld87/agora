/**
 * Run-Parameter-Query — Vertrag für alle Sender, die einen Simulationsstart
 * parametrisieren (Dashboard-Start und Schritt 2), und für Schritt 3 als
 * einzigen Empfänger.
 *
 * Slice 5 · 2026-08-02 — Fix B-09/B-27 (Runden/Tage überlebten Schritt 2→3 nicht).
 * Issue #1234 · 2026-08-11 — der Dashboard-Start kommt dazu (Rundenzahl + Budget).
 *
 * Step 2 emittiert ``next-step`` mit den Werten, die der Nutzer gegen den
 * Auto-Vorschlag gesetzt hat. Der Wrapper verwarf sie bisher kommentarlos und
 * navigierte nur mit ``simulationId`` weiter; die Props ``maxRounds`` und
 * ``simulationDays`` an Step3Simulation blieben deshalb dauerhaft undefined.
 *
 * Warum Query und nicht der pendingUpload-Store: Step 3 ist eine eigene Route,
 * auf der eine laufende Simulation beobachtet wird. Ein Reload dort darf die
 * eingestellte Rundenzahl nicht verlieren. Der Store ist bloß ``reactive`` und
 * nicht persistiert — schlimmer noch, er gehört fachlich Schritt 1 (Dateien,
 * Requirement) und wird dort nach dem Upload absichtlich geleert
 * (``useGraphBuildPipeline`` → ``clearPendingUpload``). Schritt 3 las
 * anschließend Reset-Defaults: die Dashboard-Rundenzahl wurde still zu 10, das
 * Run-Budget aus #764 erreichte ``/api/simulation/start`` nie (Issue #1234).
 *
 * Diese Datei ist die einzige Stelle, an der die Query-Schlüssel definiert
 * werden — genau der implizite Schlüsseltausch zwischen zwei Seiten war die
 * Ursache des Bugs.
 */
import { RunBudgetConfigSchema, type RunBudgetConfig } from './runBudgetContract'

export const MAX_ROUNDS_QUERY_KEY = 'maxRounds'
export const SIMULATION_DAYS_QUERY_KEY = 'simulationDays'
export const BUDGET_QUERY_KEY = 'budget'

/**
 * Obergrenze für Simulationstage — gespiegelt aus
 * ``backend/app/api/simulation_run.py`` ("simulation_days must be between
 * 1 and 365"). Ein größerer Wert lässt jeden Start am Backend scheitern;
 * er darf deshalb hier gar nicht erst durchgereicht werden, sondern fällt
 * auf den Auto-Wert zurück. Für ``max_rounds`` prüft das Backend nur auf
 * "positiv" — dort gibt es folglich keine Obergrenze zu spiegeln.
 */
export const MAX_SIMULATION_DAYS = 365

export interface RunParams {
  /** Vom Nutzer überstimmte Rundenzahl; ``null`` = Auto-Wert des Backends gilt. */
  maxRounds: number | null
  /** Vom Nutzer überstimmte Simulationstage; ``null`` = Auto-Wert des Backends gilt. */
  simulationDays: number | null
  /** Run-Budget aus dem Dashboard-Start; ``null`` = Lauf ohne Limit. */
  budget: RunBudgetConfig | null
}

/** Query-Werte sind laut vue-router string, Array oder fehlend. */
export type QueryValue = string | (string | null)[] | null | undefined

/**
 * Normalisiert einen Wert auf eine positive Ganzzahl innerhalb ``max``.
 *
 * Alles andere (0, negativ, Kommazahl, leer, NaN, Boolean, Mehrfach-Query,
 * oberhalb ``max``) gilt als "nicht gesetzt" und fällt auf ``null`` — ein
 * unsinniger URL-Wert darf nicht als Rundenzahl an das Backend gehen.
 *
 * Strings werden bewusst nur als reine Dezimalziffern akzeptiert. ``Number()``
 * allein parst auch ``'0x10'``, ``'1e2'`` und ``'+5'`` zu gültigen Ganzzahlen;
 * eine so verschleierte URL soll die eingestellte Rundenzahl nicht ersetzen.
 */
export function coercePositiveInt(value: unknown, max?: number): number | null {
  const raw = Array.isArray(value) ? value[0] : value
  const withinBounds = (n: number): number | null =>
    max !== undefined && n > max ? null : n

  if (typeof raw === 'number') {
    return Number.isInteger(raw) && raw > 0 ? withinBounds(raw) : null
  }
  if (typeof raw !== 'string' || !/^\d+$/.test(raw.trim())) {
    return null
  }
  const parsed = Number(raw.trim())
  return Number.isSafeInteger(parsed) && parsed > 0 ? withinBounds(parsed) : null
}

/**
 * Normalisiert einen Query-Wert auf ein gültiges Run-Budget.
 *
 * Das Budget ist als kompaktes JSON in *einem* Schlüssel unterwegs und nicht in
 * sechs Einzelschlüsseln: ``RunBudgetConfig`` ist ein versionierter Vertrag mit
 * eigenem Zod-Schema. Eine flache Query-Darstellung wäre eine zweite,
 * unabhängig driftende Beschreibung desselben Objekts.
 *
 * Die URL ist Nutzereingabe: geparst wird gegen ``RunBudgetConfigSchema``
 * (``.strict()``), alles andere fällt auf ``null``. Ein manipulierter Wert darf
 * nicht als Budget an ``/api/simulation/start`` gehen.
 */
function coerceBudgetObject(value: unknown): RunBudgetConfig | null {
  const result = RunBudgetConfigSchema.safeParse(value)
  return result.success ? result.data : null
}

export function coerceBudget(value: unknown): RunBudgetConfig | null {
  const raw = Array.isArray(value) ? value[0] : value
  if (typeof raw !== 'string' || raw.trim().length === 0) {
    return null
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  return coerceBudgetObject(parsed)
}

/** Liest die Run-Parameter aus einer Router-Query (Step-3-Seite). */
export function readRunParamsFromQuery(
  query: Record<string, QueryValue> | undefined | null,
): RunParams {
  return {
    maxRounds: coercePositiveInt(query?.[MAX_ROUNDS_QUERY_KEY]),
    simulationDays: coercePositiveInt(
      query?.[SIMULATION_DAYS_QUERY_KEY],
      MAX_SIMULATION_DAYS,
    ),
    budget: coerceBudget(query?.[BUDGET_QUERY_KEY]),
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
  budget?: unknown
}): Record<string, string> {
  const query: Record<string, string> = {}

  const maxRounds = coercePositiveInt(source?.maxRounds)
  if (maxRounds !== null) {
    query[MAX_ROUNDS_QUERY_KEY] = String(maxRounds)
  }
  const simulationDays = coercePositiveInt(
    source?.simulationDays,
    MAX_SIMULATION_DAYS,
  )
  if (simulationDays !== null) {
    query[SIMULATION_DAYS_QUERY_KEY] = String(simulationDays)
  }
  // Sender geben das Budget als Objekt herein (HeroNewRun), Zwischenstationen
  // als bereits serialisierten Query-Wert. Beide Formen laufen durch dieselbe
  // Validierung — ein unterwegs manipulierter Wert wird hier verworfen und
  // nicht bloß weitergereicht.
  const budget =
    typeof source?.budget === 'string'
      ? coerceBudget(source.budget)
      : coerceBudgetObject(source?.budget)
  if (budget !== null) {
    query[BUDGET_QUERY_KEY] = JSON.stringify(budget)
  }
  return query
}
