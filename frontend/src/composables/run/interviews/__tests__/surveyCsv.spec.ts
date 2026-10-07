import { describe, expect, it } from 'vitest'
import { buildSurveyCsv, csvCell, surveyCsvFilename } from '../surveyCsv'

describe('csvCell', () => {
  it('setzt jede Zelle in Anführungszeichen und verdoppelt enthaltene', () => {
    expect(csvCell('sagt "ja"')).toBe('"sagt ""ja"""')
  })

  it('erhält Zeilenumbrüche, Komma und Semikolon innerhalb der Zelle', () => {
    expect(csvCell('a,b;c\nd')).toBe('"a,b;c\nd"')
  })

  it('entschärft Formelzeichen am Zellanfang mit vorangestelltem Apostroph', () => {
    expect(csvCell('=SUMME(A1)')).toBe(`"'=SUMME(A1)"`)
    expect(csvCell('+1')).toBe(`"'+1"`)
    expect(csvCell('-2')).toBe(`"'-2"`)
    expect(csvCell('@x')).toBe(`"'@x"`)
    expect(csvCell('\t=x')).toBe(`"'\t=x"`)
  })

  it('lässt Formelzeichen mitten im Text unverändert', () => {
    expect(csvCell('a=b')).toBe('"a=b"')
  })

  it('macht aus null eine leere Zelle', () => {
    expect(csvCell(null)).toBe('""')
  })
})

describe('buildSurveyCsv', () => {
  it('schreibt Kopfzeile agent_id,username,question,answer,error und je Persona eine Zeile', () => {
    const csv = buildSurveyCsv([
      { agentId: 0, name: 'Anke', question: 'Frage?', answer: 'Ja', error: null },
      { agentId: 1, name: 'Jörg', question: 'Frage?', answer: null, error: 'kaputt' },
    ])
    expect(csv.split('\n')).toEqual([
      '"agent_id","username","question","answer","error"',
      '"0","Anke","Frage?","Ja",""',
      '"1","Jörg","Frage?","","kaputt"',
    ])
  })

  it('hält mehrzeilige Antworten in einer Zelle', () => {
    const csv = buildSurveyCsv([{ agentId: 2, name: 'X', question: 'q', answer: 'a\nb', error: null }])
    expect(csv).toContain('"a\nb"')
  })
})

describe('surveyCsvFilename', () => {
  it('folgt dem Muster agora-survey-<Zeitstempel>.csv', () => {
    expect(surveyCsvFilename(1790000000000)).toBe('agora-survey-1790000000000.csv')
  })
})
