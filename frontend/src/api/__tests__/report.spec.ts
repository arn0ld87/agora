import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()

vi.mock('../index', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
  },
  requestWithRetry: vi.fn(),
}))

import { getReportEvidence } from '../report'
import { isApiError } from '../envelope'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getReportEvidence (Issue #1477 F1)', () => {
  it('parses a valid success envelope against EvidenceMapResponseSchema', async () => {
    const validEnvelope = {
      success: true,
      data: {
        schema_version: 3,
        report_id: 'report-1',
        simulation_id: 'sim-1',
        evidence_index: {},
        global_evidence_refs: [],
        sections: [],
      },
    }
    mockGet.mockResolvedValue(validEnvelope)

    const result = await getReportEvidence('report-1')

    expect(result).toEqual({
      success: true,
      data: {
        schema_version: 3,
        report_id: 'report-1',
        simulation_id: 'sim-1',
        evidence_index: {},
        global_evidence_refs: [],
        sections: [],
        degradation_log: [],
        gate_decision_log: [],
        evidence_coverage_ledger: [],
      },
    })
  })

  it('passes the error envelope through unparsed', async () => {
    const errorEnvelope = { success: false, code: 'not_found', error: 'kein Report' }
    mockGet.mockResolvedValue(errorEnvelope)

    const result = await getReportEvidence('report-1')

    expect(result).toEqual(errorEnvelope)
  })

  it('applies the validation_errors default for an omission without that field', async () => {
    const omissionEnvelope = {
      success: true,
      evidence_omitted: { reason: 'contract_violation', detail: 'kaputt' },
    }
    mockGet.mockResolvedValue(omissionEnvelope)

    const result = await getReportEvidence('report-1')

    expect(result).toEqual({
      success: true,
      evidence_omitted: { reason: 'contract_violation', detail: 'kaputt', validation_errors: [] },
    })
  })

  it('throws a defined error instead of silently returning a drifting envelope', async () => {
    // Vertragswidrig: weder `data` noch `evidence_omitted` gesetzt.
    const driftingEnvelope = { success: true }
    mockGet.mockResolvedValue(driftingEnvelope)

    await expect(getReportEvidence('report-1')).rejects.toThrow(/schema mismatch/)
  })

  // Review B7 (PR #1477 F1): der geworfene Fehler muss von einem
  // Transport-/HTTP-Fehler unterscheidbar sein, sonst behandelt
  // `Step4Report.loadEvidence()` einen Schema-Mismatch faelschlich als
  // transienten Zustand und plant einen unbegrenzten Retry statt
  // `recordSchemaError` aufzurufen.
  it('throws an ApiError with code "schema_mismatch" for a drifting envelope, not a plain Error', async () => {
    const driftingEnvelope = { success: true }
    mockGet.mockResolvedValue(driftingEnvelope)

    let caught: unknown
    try {
      await getReportEvidence('report-1')
    } catch (err) {
      caught = err
    }

    expect(isApiError(caught)).toBe(true)
    expect((caught as { code?: string }).code).toBe('schema_mismatch')
  })
})
