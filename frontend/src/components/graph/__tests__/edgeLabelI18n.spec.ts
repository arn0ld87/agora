// Issue #129 / SUB1 — Edge-Label-i18n.
//
// Sichert ab, dass `formatEdgeLabel` zuerst die i18n-Map nutzt und nur dann
// auf eine Heuristik zurückfällt, wenn der Lookup misslingt.

import { describe, it, expect, vi } from 'vitest'

import {
  formatEdgeLabel,
  humanizeEdgeKey,
  normalizeEdgeKey,
} from '../edgeLabelI18n'

const fakeT = (map: Record<string, string>) => (key: string) => (key in map ? map[key] : key)

describe('normalizeEdgeKey', () => {
  it('normalisiert UPPER_SNAKE-Werte unverändert', () => {
    expect(normalizeEdgeKey('WORKS_FOR')).toBe('WORKS_FOR')
  })

  it('konvertiert camelCase zu UPPER_SNAKE', () => {
    expect(normalizeEdgeKey('worksFor')).toBe('WORKS_FOR')
  })

  it('konvertiert "Works for" zu UPPER_SNAKE', () => {
    expect(normalizeEdgeKey('Works for')).toBe('WORKS_FOR')
  })

  it('liefert leeren String für leere Eingabe', () => {
    expect(normalizeEdgeKey('')).toBe('')
    expect(normalizeEdgeKey(null)).toBe('')
    expect(normalizeEdgeKey(undefined)).toBe('')
  })
})

describe('humanizeEdgeKey', () => {
  it('erzeugt Title-Case aus UPPER_SNAKE', () => {
    expect(humanizeEdgeKey('WORKS_FOR')).toBe('Works For')
    expect(humanizeEdgeKey('RELATES_TO')).toBe('Relates To')
  })

  it('verträgt einzelne Wörter', () => {
    expect(humanizeEdgeKey('KNOWS')).toBe('Knows')
  })

  it('liefert leeren String für leere Eingabe', () => {
    expect(humanizeEdgeKey('')).toBe('')
  })
})

describe('formatEdgeLabel', () => {
  it('liefert übersetzten Wert, wenn i18n-Map einen Eintrag hat', () => {
    const t = fakeT({
      'graph.edgeLabels.WORKS_FOR': 'arbeitet für',
    })
    expect(formatEdgeLabel('WORKS_FOR', t)).toBe('arbeitet für')
  })

  it('akzeptiert auch camelCase / Title-Case Roh-Eingaben', () => {
    const t = fakeT({
      'graph.edgeLabels.WORKS_FOR': 'arbeitet für',
    })
    expect(formatEdgeLabel('worksFor', t)).toBe('arbeitet für')
    expect(formatEdgeLabel('Works for', t)).toBe('arbeitet für')
  })

  it('fällt auf Heuristik zurück, wenn i18n-Lookup misslingt', () => {
    const t = fakeT({})
    expect(formatEdgeLabel('SOME_UNKNOWN_RELATION', t)).toBe('Some Unknown Relation')
  })

  it('funktioniert ohne i18n-Hook', () => {
    expect(formatEdgeLabel('WORKS_FOR')).toBe('Works For')
  })

  it('verträgt leere und ungültige Eingaben', () => {
    expect(formatEdgeLabel('', fakeT({}))).toBe('')
    expect(formatEdgeLabel(null, fakeT({}))).toBe('')
    expect(formatEdgeLabel(undefined, fakeT({}))).toBe('')
  })

  // Issue #1023 (Befund B-04): formatEdgeLabel() rief t(fullKey) fuer jede
  // LLM-generierte, nicht in graph.edgeLabels hinterlegte Relation auf —
  // vue-i18n loggt das im Dev-Modus als "not found"-Warnung, bevor
  // humanizeEdgeKey() ueberhaupt greift. Der te()-Guard verhindert den
  // t()-Aufruf strukturell, statt sich auf das Miss-Verhalten zu verlassen.
  it('ruft t() nicht auf, wenn te() den Key als fehlend meldet', () => {
    const t = vi.fn((key: string) => key)
    const te = vi.fn(() => false)
    expect(formatEdgeLabel('SOME_UNKNOWN_RELATION', t, te)).toBe('Some Unknown Relation')
    expect(te).toHaveBeenCalledWith('graph.edgeLabels.SOME_UNKNOWN_RELATION')
    expect(t).not.toHaveBeenCalled()
  })

  it('ruft t() auf, wenn te() den Key als vorhanden meldet', () => {
    const t = vi.fn(() => 'arbeitet für')
    const te = vi.fn(() => true)
    expect(formatEdgeLabel('WORKS_FOR', t, te)).toBe('arbeitet für')
    expect(t).toHaveBeenCalledWith('graph.edgeLabels.WORKS_FOR')
  })
})
