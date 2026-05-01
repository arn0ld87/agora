// Issue #129 / SUB1 — Edge-Label-i18n.
//
// Sichert ab, dass `formatEdgeLabel` zuerst die i18n-Map nutzt und nur dann
// auf eine Heuristik zurückfällt, wenn der Lookup misslingt.

import { describe, it, expect } from 'vitest'

import {
  formatEdgeLabel,
  humanizeEdgeKey,
  normalizeEdgeKey,
} from '../edgeLabelI18n'

const fakeT = (map) => (key) => (key in map ? map[key] : key)

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
})
