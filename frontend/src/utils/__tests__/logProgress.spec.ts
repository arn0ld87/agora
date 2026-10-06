import { describe, it, expect } from 'vitest'
import { collapseProgressLines, isProgressLine, lastCarriageReturnState } from '../logProgress'

describe('logProgress', () => {
  it('nimmt bei Wagenrücklauf den letzten nichtleeren Stand', () => {
    expect(lastCarriageReturnState('  0%|     | 0/10\r 50%|█████| 5/10\r100%|██████████| 10/10\r')).toBe(
      '100%|██████████| 10/10',
    )
    expect(lastCarriageReturnState('normal')).toBe('normal')
  })

  it('erkennt Balkenzeilen, aber keine bloßen Prozentangaben', () => {
    expect(isProgressLine('Downloading:  45%|████▌     | 9/20 [00:03<00:04, 2.9it/s]')).toBe(true)
    expect(isProgressLine('Budget 45% verbraucht')).toBe(false)
  })

  it('fasst eine überschriebene Zeile zu einer Zeile zusammen', () => {
    const out = collapseProgressLines([
      'INFO start',
      'twhin-bert:   0%|    | 0/4\rtwhin-bert:  50%|██  | 2/4\rtwhin-bert: 100%|████| 4/4\r',
      'INFO fertig',
    ])
    expect(out).toEqual(['INFO start', 'twhin-bert: 100%|████| 4/4', 'INFO fertig'])
  })

  it('fasst aufeinanderfolgende Balkenzeilen gleicher Beschriftung zusammen', () => {
    const out = collapseProgressLines([
      'Laden:  10%|█   | 1/10',
      'Laden:  50%|█████| 5/10',
      'Laden: 100%|██████████| 10/10',
    ])
    expect(out).toEqual(['Laden: 100%|██████████| 10/10'])
  })

  it('hält Balken mit unterschiedlicher Beschriftung oder Zwischenzeilen getrennt', () => {
    const out = collapseProgressLines([
      'A:  10%|█   | 1/10',
      'B:  20%|██  | 2/10',
      'INFO dazwischen',
      'B:  30%|███ | 3/10',
    ])
    expect(out).toEqual(['A:  10%|█   | 1/10', 'B:  20%|██  | 2/10', 'INFO dazwischen', 'B:  30%|███ | 3/10'])
  })

  it('lässt normale Zeilen unverändert', () => {
    expect(collapseProgressLines(['a', 'b'])).toEqual(['a', 'b'])
    expect(collapseProgressLines([])).toEqual([])
  })
})
