/**
 * CSV-Export der Umfrage (Gruppenfrage) im Interviews-Reiter (#1790). Rein, ohne Vue.
 *
 * Format wie in der früheren Altansicht (`Step5Interaction`): Komma als
 * Trenner, jede Zelle in Anführungszeichen, `"` verdoppelt, Zeilenende `\n`,
 * Spalten `agent_id,username,question,answer`, Dateiname
 * `agora-survey-<Zeitstempel>.csv`. Neu: die Spalte `error` (Teilfehler je
 * Persona stehen dort, `answer` bleibt dann leer) und der Schutz vor
 * Formel-Injection (die Altansicht hatte keinen): beginnt eine Zelle mit `=`,
 * `+`, `-`, `@`, Tab oder CR, steht ein `'` davor.
 */

export interface SurveyCsvRow {
  agentId: number
  name: string
  question: string
  answer: string | null
  error: string | null
}

export const SURVEY_CSV_HEADER = ['agent_id', 'username', 'question', 'answer', 'error'] as const

const FORMULA_START = /^[=+\-@\t\r]/

export function csvCell(value: string | number | null | undefined): string {
  let text = String(value ?? '')
  if (FORMULA_START.test(text)) text = `'${text}`
  return `"${text.replace(/"/g, '""')}"`
}

export function buildSurveyCsv(rows: readonly SurveyCsvRow[]): string {
  const lines = [SURVEY_CSV_HEADER.map(csvCell).join(',')]
  for (const r of rows) {
    lines.push([r.agentId, r.name, r.question, r.answer, r.error].map(csvCell).join(','))
  }
  return lines.join('\n')
}

export function surveyCsvFilename(now: number = Date.now()): string {
  return `agora-survey-${now}.csv`
}
