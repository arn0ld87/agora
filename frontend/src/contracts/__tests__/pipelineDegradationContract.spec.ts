import { describe, it, expect } from 'vitest'
import {
  DEGRADATION_KINDS,
  EMPTY_DEGRADATION_REPORT,
  PipelineDegradationReportSchema,
  PipelineDegradationSchema,
  hasBlockingDegradation,
  parseDegradationReport,
} from '../pipelineDegradationContract'

/**
 * Zod-Spiegel zu `backend/app/contracts/pipeline_degradation_contract.py`
 * (Issue #1029). Die Enum-Werte sind Vertragsbestandteil — driften sie
 * auseinander, verschwindet der Hinweis wortlos, und genau das war der
 * Ausgangsbefund.
 */

const validEvent = {
  kind: 'embedding_unavailable' as const,
  severity: 'warning' as const,
  detail: 'Batch-Embedding fehlgeschlagen.',
  occurred_at: '2026-08-02T20:00:00Z',
  occurrences: 3,
  context: { affected_texts: 12 },
}

describe('PipelineDegradationSchema', () => {
  it('akzeptiert ein vollständiges Ereignis', () => {
    const parsed = PipelineDegradationSchema.parse(validEvent)
    expect(parsed.kind).toBe('embedding_unavailable')
    expect(parsed.occurrences).toBe(3)
  })

  it('setzt occurrences und context per Default', () => {
    const parsed = PipelineDegradationSchema.parse({
      kind: 'graph_below_threshold',
      severity: 'blocking',
      detail: 'Graph ohne Kanten.',
      occurred_at: '2026-08-02T20:00:00Z',
    })
    expect(parsed.occurrences).toBe(1)
    expect(parsed.context).toEqual({})
  })

  it('weist unbekannte Felder ab', () => {
    const result = PipelineDegradationSchema.safeParse({ ...validEvent, extra: 'nope' })
    expect(result.success).toBe(false)
  })

  it('weist eine unbekannte Art ab', () => {
    const result = PipelineDegradationSchema.safeParse({ ...validEvent, kind: 'was_neues' })
    expect(result.success).toBe(false)
  })

  it('weist ein leeres detail ab', () => {
    const result = PipelineDegradationSchema.safeParse({ ...validEvent, detail: '' })
    expect(result.success).toBe(false)
  })

  it('spiegelt exakt die Backend-Arten', () => {
    expect([...DEGRADATION_KINDS]).toEqual([
      'embedding_unavailable',
      'graph_below_threshold',
      'persona_rule_based_fallback',
    ])
  })
})

describe('PipelineDegradationReportSchema', () => {
  it('parst einen leeren Report', () => {
    const parsed = PipelineDegradationReportSchema.parse({ schema_version: 1, events: [] })
    expect(parsed.events).toEqual([])
  })

  it('setzt Defaults bei einem leeren Objekt', () => {
    const parsed = PipelineDegradationReportSchema.parse({})
    expect(parsed.schema_version).toBe(1)
    expect(parsed.events).toEqual([])
  })
})

describe('parseDegradationReport', () => {
  it('liest das Feld aus einem Task-Ergebnis', () => {
    const report = parseDegradationReport({
      graph_id: 'g1',
      degradations: { schema_version: 1, events: [validEvent] },
    })
    expect(report.events).toHaveLength(1)
  })

  it('liefert einen leeren Report, wenn das Feld fehlt', () => {
    // Task-Ergebnisse von vor #1029 tragen es nicht.
    expect(parseDegradationReport({ graph_id: 'g1' })).toEqual(EMPTY_DEGRADATION_REPORT)
  })

  it('liefert einen leeren Report bei null oder undefined', () => {
    expect(parseDegradationReport(null)).toEqual(EMPTY_DEGRADATION_REPORT)
    expect(parseDegradationReport(undefined)).toEqual(EMPTY_DEGRADATION_REPORT)
  })

  it('schluckt kaputte Daten statt zu werfen', () => {
    // Ein Hinweismechanismus darf nie selbst zum Ausfallgrund werden.
    expect(parseDegradationReport({ degradations: 'kaputt' })).toEqual(EMPTY_DEGRADATION_REPORT)
    expect(parseDegradationReport({ degradations: { events: [{ kind: 'unbekannt' }] } }))
      .toEqual(EMPTY_DEGRADATION_REPORT)
  })
})

describe('hasBlockingDegradation', () => {
  it('ist false bei einem leeren Report', () => {
    expect(hasBlockingDegradation(EMPTY_DEGRADATION_REPORT)).toBe(false)
  })

  it('ist false, wenn nur Warnungen vorliegen', () => {
    expect(hasBlockingDegradation({ schema_version: 1, events: [validEvent] })).toBe(false)
  })

  it('ist true, sobald ein Ereignis blockiert', () => {
    const report = {
      schema_version: 1,
      events: [
        validEvent,
        { ...validEvent, kind: 'graph_below_threshold' as const, severity: 'blocking' as const },
      ],
    }
    expect(hasBlockingDegradation(report)).toBe(true)
  })
})
