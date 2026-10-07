/**
 * Zeilenarten des Protokolls für die Diagnose der Simulation (#1801).
 *
 * `classifyLogLine` ordnet eine Zeile einer Art zu, `collapseProgress` verdichtet
 * Fortschrittsbalken zu einer Zeile mit Anzahl. Beides sind reine Funktionen.
 *
 * Belegte Zeilenformen (Backend):
 * - Tool-Call, Webprozess:   `Executing tool: <name>, parameters: …`
 *   (backend/app/services/tool_execution.py, `logger.info`) und
 *   `Tool execution failed: <name>, error: …` (ebenda, `logger.error`).
 * - Tool-Call, Simulationsprozess: `[ToolUse] Agent calling <name>(<params>)`,
 *   `[ToolUse]   -> OK|ERROR: …` (backend/scripts/agent_tools.py) und die
 *   `[ToolUse] …`-Meldungen in backend/scripts/sim_runtime/platform_runner.py.
 * - Fehler: Schlüsselwörter aus `utils/errorLinePattern` (error, exception,
 *   traceback, fatal, warn, warning), also auch Warnungen.
 * - Fortschritt: tqdm-Balken `NN%|████ |` (utils/logProgress).
 */
import { isErrorLine } from '@/utils/errorLinePattern'
import { isProgressLine, lastCarriageReturnState, progressLabel } from '@/utils/logProgress'

export type LogLineKind = 'error' | 'toolCall' | 'progress' | 'other'

const TOOL_CALL_RE = /\[ToolUse\]|\bExecuting tool:|\bTool execution failed:/

/** Reihenfolge: Fehler vor Tool-Call vor Fortschritt. */
export function classifyLogLine(line: unknown): LogLineKind {
  if (typeof line !== 'string') return 'other'
  if (isErrorLine(line)) return 'error'
  if (TOOL_CALL_RE.test(line)) return 'toolCall'
  if (isProgressLine(line)) return 'progress'
  return 'other'
}

export interface CollapsedLine {
  /** Letzter Stand der Zeile (bei Balken: der zuletzt gemeldete). */
  line: string
  /** Anzahl der Quellzeilen, die hier zusammenlaufen; 1 = unverändert. */
  count: number
}

/**
 * Fasst aufeinanderfolgende Fortschrittszeilen gleicher Beschriftung und per
 * `\r` überschriebene Zwischenstände zu einer Zeile zusammen. Alle anderen
 * Zeilen bleiben unverändert in Reihenfolge. Die Anzahl zählt jede Quellzeile
 * und jeden `\r`-Zwischenstand.
 */
export function collapseProgress(lines: readonly string[]): CollapsedLine[] {
  const out: CollapsedLine[] = []
  let prevLabel: string | null = null
  for (const raw of lines) {
    if (typeof raw !== 'string') {
      prevLabel = null
      continue
    }
    const state = lastCarriageReturnState(raw)
    if (!isProgressLine(state)) {
      out.push({ line: state, count: 1 })
      prevLabel = null
      continue
    }
    const steps = raw.includes('\r') ? raw.split('\r').filter((p) => p.trim() !== '').length : 1
    const label = progressLabel(state)
    const last = out[out.length - 1]
    if (prevLabel !== null && prevLabel === label && last) {
      last.line = state
      last.count += steps
    } else {
      out.push({ line: state, count: steps })
    }
    prevLabel = label
  }
  return out
}

/**
 * Vorfilter für `LogStream` (optional): zeigt nur die genannten Zeilenarten,
 * verdichtet Fortschrittsbalken mit Anzahl und bietet „Alles anzeigen“.
 * Die Texte kommen vom Aufrufer, damit `LogStream` keine neuen Schlüssel braucht.
 */
export interface LogKindFilter {
  kinds: readonly LogLineKind[]
  toggleLabel: string
  collapsedLabel: (count: number) => string
}
