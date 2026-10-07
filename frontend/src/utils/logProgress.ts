/**
 * logProgress — rohe Fortschrittsbalken (tqdm-artig) im Protokoll
 * zusammenfassen.
 *
 * Fortschrittsbalken überschreiben sich per Wagenrücklauf (`\r`) in derselben
 * Zeile; in der Logdatei landet jeder Zwischenstand hintereinander. Die
 * Konsole zeigt davon nur den letzten Stand. Reine Funktion, ohne Zustand.
 */

// "  45%|████▌     | 9/20 [00:03<00:04, 2.9it/s]" und Varianten ohne Prozent.
const PROGRESS_RE = /\d+%\|[^|]*\|/

/** Letzter nichtleerer Abschnitt einer Zeile, die per `\r` überschrieben wurde. */
export function lastCarriageReturnState(line: string): string {
  if (!line.includes('\r')) return line
  const parts = line.split('\r')
  for (let i = parts.length - 1; i >= 0; i--) {
    const part = parts[i]
    if (part !== undefined && part.trim() !== '') return part
  }
  return ''
}

/** Ist die Zeile ein Fortschrittsbalken (Balken-Muster, nicht nur ein Prozentwert)? */
export function isProgressLine(line: string): boolean {
  return PROGRESS_RE.test(lastCarriageReturnState(line))
}

/** Text vor dem Prozentwert; gleiche Beschriftung = gleicher Balken. */
export function progressLabel(line: string): string {
  const state = lastCarriageReturnState(line)
  const idx = state.search(/\d+%\|/)
  return idx > 0 ? state.slice(0, idx).trim() : ''
}

/**
 * Fasst Fortschrittsbalken zusammen: per `\r` überschriebene Zustände
 * innerhalb einer Zeile bleiben als letzter Stand, aufeinanderfolgende
 * Balkenzeilen mit gleicher Beschriftung ergeben eine Zeile mit dem letzten Stand.
 * Alle übrigen Zeilen bleiben unverändert und in Reihenfolge.
 */
export function collapseProgressLines(lines: readonly string[]): string[] {
  const out: string[] = []
  let prevProgressLabel: string | null = null
  for (const raw of lines) {
    if (typeof raw !== 'string') {
      out.push(raw)
      prevProgressLabel = null
      continue
    }
    const line = lastCarriageReturnState(raw)
    if (isProgressLine(line)) {
      const label = progressLabel(line)
      if (prevProgressLabel !== null && prevProgressLabel === label && out.length > 0) {
        out[out.length - 1] = line
      } else {
        out.push(line)
      }
      prevProgressLabel = label
    } else {
      out.push(line)
      prevProgressLabel = null
    }
  }
  return out
}
