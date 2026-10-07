import { describe, expect, it } from 'vitest'
import { classifyLogLine, collapseProgress } from '../logKinds'

describe('classifyLogLine', () => {
  it('erkennt Tool-Calls des Webprozesses (tool_execution.py)', () => {
    expect(
      classifyLogLine("[2026-10-07 10:00:00] INFO [app.services.tool_execution.execute_tool:216] Executing tool: graph_search, parameters: {'q': 'x'}"),
    ).toBe('toolCall')
  })

  it('erkennt Tool-Calls des Simulationsprozesses (agent_tools.py, platform_runner.py)', () => {
    expect(classifyLogLine("[ToolUse] Agent calling search_graph({'query': 'Wärmepumpe'})")).toBe('toolCall')
    expect(classifyLogLine('[ToolUse]   -> OK')).toBe('toolCall')
    expect(classifyLogLine('[ToolUse] Agent tools enabled — initializing tool registry...')).toBe('toolCall')
  })

  it('stuft fehlgeschlagene Tool-Calls als Fehler ein (Fehler vor Tool-Call)', () => {
    expect(classifyLogLine('[ToolUse]   -> ERROR: timeout')).toBe('error')
    expect(classifyLogLine('ERROR Tool execution failed: graph_search, error: boom')).toBe('error')
  })

  it('erkennt Fehler und Warnungen, aber keine Wort-Innenstücke', () => {
    expect(classifyLogLine('Traceback (most recent call last):')).toBe('error')
    expect(classifyLogLine('WARNING langsame Antwort')).toBe('error')
    expect(classifyLogLine('errorless forwarded')).toBe('other')
  })

  it('erkennt tqdm-Fortschritt, aber keine bloße Prozentangabe', () => {
    expect(classifyLogLine('Batches:  45%|████▌     | 9/20 [00:03<00:04, 2.9it/s]')).toBe('progress')
    expect(classifyLogLine('Budget 45% verbraucht')).toBe('other')
  })

  it('behandelt Nicht-Strings und normale Zeilen als other', () => {
    expect(classifyLogLine(undefined)).toBe('other')
    expect(classifyLogLine('INFO Simulation gestartet')).toBe('other')
  })
})

describe('collapseProgress', () => {
  it('verdichtet aufeinanderfolgende Balkenzeilen gleicher Beschriftung mit Anzahl', () => {
    expect(
      collapseProgress([
        'INFO start',
        'Laden:  10%|█   | 1/10',
        'Laden:  50%|█████| 5/10',
        'Laden: 100%|██████████| 10/10',
        'INFO fertig',
      ]),
    ).toEqual([
      { line: 'INFO start', count: 1 },
      { line: 'Laden: 100%|██████████| 10/10', count: 3 },
      { line: 'INFO fertig', count: 1 },
    ])
  })

  it('zählt \\r-Zwischenstände und nimmt den letzten Stand', () => {
    expect(
      collapseProgress(['twhin-bert:   0%|    | 0/4\rtwhin-bert:  50%|██  | 2/4\rtwhin-bert: 100%|████| 4/4\r']),
    ).toEqual([{ line: 'twhin-bert: 100%|████| 4/4', count: 3 }])
  })

  it('trennt Balken mit verschiedener Beschriftung und Balken, die eine andere Zeile unterbricht', () => {
    const out = collapseProgress([
      'A:  10%|█| 1/10',
      'B:  20%|██| 2/10',
      'INFO dazwischen',
      'B:  30%|███| 3/10',
    ])
    expect(out.map((o) => o.count)).toEqual([1, 1, 1, 1])
  })

  it('lässt normale Zeilen unverändert und gibt bei leerer Eingabe nichts zurück', () => {
    expect(collapseProgress([])).toEqual([])
    expect(collapseProgress(['a', 'b'])).toEqual([
      { line: 'a', count: 1 },
      { line: 'b', count: 1 },
    ])
  })
})
