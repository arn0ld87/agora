/**
 * errorLinePattern — Wortgrenzen-bewusstes Matchen von Logzeilen-Token,
 * die typischerweise auf Fehler hindeuten.
 *
 * Vor diesem Fix matchte das Pattern Wort-INNERE Vorkommen, etwa
 * "forwarded", "errorless", "warningless" oder "awareness". Diese
 * Wort-Inneren Treffer führten in LogDrawer, SimulationToolPanel und
 * Step3Simulation zu falsch klassifizierten Error-Zähler und Filter-
 * Ergebnissen.
 *
 * Pattern (Wortgrenzen via \b):
 *  - \b am Anfang: kein Buchstabe/Ziffer vor dem Token.
 *  - \b am Ende:   kein Buchstabe/Ziffer nach dem Token.
 *  - Gleicher Token-Satz in allen Konsumenten (LogDrawer, Step3Simulation,
 *    SimulationToolPanel) — vorher divergierten sie (LogDrawer hatte
 *    warn|warning nicht).
 */
export const ERROR_PATTERN = /\b(?:error|exception|traceback|fatal|warn|warning)\b/i

/**
 * Erkennt, ob eine Zeile ein Fehler- oder Warnschlüsselwort enthält.
 *
 * @param line - Zu prüfender Wert
 * @returns `true`, wenn `line` eine Zeichenkette mit einem Fehler- oder Warnschlüsselwort ist, andernfalls `false`
 */
export function isErrorLine(line: unknown): boolean {
  return typeof line === 'string' && ERROR_PATTERN.test(line)
}
