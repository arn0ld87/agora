import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { ApiError } from '@/api/envelope'
import {
  REPORT_GENERATE_IN_PROGRESS_CODE,
  classifyEvidenceEnvelope,
  classifyEvidenceError,
  classifyReportEnvelope,
  classifyReportLoadError,
  describeReportError,
  extractAttachableRunningReportId,
  formatSchemaIssues,
  isActiveRegistryRunForReport,
  isGenerateInProgressError,
  isReportRunningStatus,
  isReportTerminalStatus,
  isReportTerminalWithEvidence,
  isUnsavedNotFoundError,
} from '../reportViewState'

describe('reportViewState deep module', () => {
  it('classifies report running and terminal statuses cleanly', () => {
    expect(isReportRunningStatus('pending')).toBe(true)
    expect(isReportRunningStatus('planning')).toBe(true)
    expect(isReportRunningStatus('generating')).toBe(true)
    expect(isReportRunningStatus('completed')).toBe(false)
    expect(isReportRunningStatus(undefined)).toBe(false)

    expect(isReportTerminalWithEvidence('completed')).toBe(true)
    expect(isReportTerminalWithEvidence('incomplete')).toBe(true)
    expect(isReportTerminalWithEvidence('failed')).toBe(false)

    expect(isReportTerminalStatus('completed')).toBe(true)
    expect(isReportTerminalStatus('incomplete')).toBe(true)
    expect(isReportTerminalStatus('failed')).toBe(true)
    expect(isReportTerminalStatus('generating')).toBe(false)
  })

  it('matches active registry run status for a report id', () => {
    expect(
      isActiveRegistryRunForReport(
        {
          success: true,
          data: {
            report_id: 'rep_1',
            run_id: 'run_1',
            status: 'processing',
          },
        },
        'rep_1',
      ),
    ).toBe(true)

    expect(
      isActiveRegistryRunForReport(
        {
          success: true,
          data: {
            report_id: 'rep_1',
            run_id: 'run_1',
            status: 'completed',
          },
        },
        'rep_1',
      ),
    ).toBe(false)

    expect(
      isActiveRegistryRunForReport(
        {
          success: true,
          data: {
            report_id: 'rep_other',
            run_id: 'run_1',
            status: 'pending',
          },
        },
        'rep_1',
      ),
    ).toBe(false)
  })

  it('detects 409 report_generate_in_progress and extracts attachable report_id', () => {
    expect(isGenerateInProgressError({ code: REPORT_GENERATE_IN_PROGRESS_CODE })).toBe(true)
    expect(isGenerateInProgressError({ code: 'other_error' })).toBe(false)

    expect(
      extractAttachableRunningReportId({
        success: true,
        data: { report_id: 'rep_running', status: 'generating' },
      }),
    ).toBe('rep_running')

    expect(
      extractAttachableRunningReportId({
        success: true,
        data: { report_id: 'rep_done', status: 'completed' },
      }),
    ).toBeNull()
  })

  it('describes and classifies HTTP 404/not_found vs contract/transport errors', () => {
    const notFoundErr = new ApiError({ message: 'Report missing', status: 404, code: 'not_found' })
    expect(describeReportError(notFoundErr)).toBe('Report missing')
    expect(classifyReportLoadError(notFoundErr)).toEqual({
      kind: 'notFound',
      reason: 'Report missing',
    })
    expect(isUnsavedNotFoundError(notFoundErr)).toBe(true)
    expect(isUnsavedNotFoundError({ code: 'not_found' })).toBe(true)

    const schemaErr = new ApiError({
      message: 'Invalid payload',
      status: 422,
      code: 'schema_mismatch',
    })
    expect(classifyReportLoadError(schemaErr)).toEqual({
      kind: 'contract',
      reason: 'Invalid payload',
    })
    expect(isUnsavedNotFoundError(schemaErr)).toBe(false)
  })

  it('formats zod schema issues succinctly', () => {
    const schema = z.object({ report_id: z.string(), count: z.number() })
    const parsed = schema.safeParse({ report_id: 123, count: 'bad' })
    expect(parsed.success).toBe(false)
    if (!parsed.success) {
      const formatted = formatSchemaIssues(parsed.error)
      expect(formatted.some((line) => line.startsWith('report_id:'))).toBe(true)
      expect(formatted.some((line) => line.startsWith('count:'))).toBe(true)
    }
  })

  it('classifies report and evidence envelopes into discriminated states', () => {
    expect(
      classifyReportEnvelope('rep_404', {
        success: false,
        code: 'not_found',
        error: 'Not found',
      }),
    ).toEqual({
      status: 'failed',
      kind: 'notFound',
      reason: 'Not found',
    })
    expect(
      classifyReportEnvelope('rep_err', {
        success: false,
        code: 'internal_error',
        error: 'DB offline',
      }),
    ).toEqual({
      status: 'failed',
      kind: 'transport',
      reason: 'DB offline',
    })

    expect(
      classifyEvidenceEnvelope({
        success: false,
        code: 'not_found',
        error: 'Evidence not saved',
      } as never),
    ).toEqual({
      status: 'unsaved',
    })
    expect(
      classifyEvidenceEnvelope({
        success: false,
        error: 'Evidence failed',
      } as never),
    ).toEqual({
      status: 'failed',
      kind: 'transport',
      reason: 'Evidence failed',
    })
    expect(classifyEvidenceError(new Error('Network error'))).toEqual({
      status: 'failed',
      kind: 'transport',
      reason: 'Network error',
    })
  })
})
