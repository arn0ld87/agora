import { describe, expect, it } from 'vitest'

import reportStatusJsonSchema from '../../../../schemas/report-status-response.schema.json'

import { ReportStatusResponseSchema } from '../reportStatusContract'

/**
 * Issue #1174 (Codex-Finding 1+2) — vier der fuenf Stufen von
 * ``ReportStatusService.get_status`` lieferten bis dahin handgeschriebene
 * Dicts ohne Gegenstueck in ``schemas/*.json`` und ohne Zod-Drift-Check; die
 * Run-Registry-Stufe (hoechste Prioritaet) hatte zusaetzlich gar kein
 * ``message_key``. Dieser Test schliesst beide Luecken: jeder Feldname aus
 * dem generierten JSON-Schema muss im Zod-Spiegel vorkommen, und alle vier
 * abgedeckten Payload-Formen muessen strikt parsen.
 */
describe('reportStatusContract mirrors backend report_status_contract', () => {
  it('ReportStatusResponseSchema declares exactly the fields of report-status-response.schema.json', () => {
    const backendFields = Object.keys(reportStatusJsonSchema.properties).sort()
    const zodFields = Object.keys(ReportStatusResponseSchema.shape).sort()
    expect(zodFields).toEqual(backendFields)
  })

  it('parses the completed payload (_status_from_persisted_report / _status_from_simulation)', () => {
    const payload = {
      simulation_id: 'sim_1',
      report_id: 'rep_1',
      status: 'completed',
      progress: 100,
      message: 'Report generated',
      message_key: 'report.generated',
      already_completed: true,
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the failed payload (_status_from_persisted_report)', () => {
    const payload = {
      simulation_id: 'sim_1',
      report_id: 'rep_1',
      status: 'failed',
      progress: 0,
      message: 'Report generation failed',
      message_key: 'report.failed',
      error: 'boom',
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the acknowledge-polling payload without simulation_id', () => {
    const payload = {
      report_id: 'rep_12',
      status: 'generating',
      progress: 0,
      message: 'Task handle unknown — waiting for report completion',
      message_key: 'report.awaiting_task',
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses the Run-Registry payload with outline/sections and the new message_key (Finding 2)', () => {
    const payload = {
      simulation_id: 'sim_1',
      report_id: 'rep_1',
      run_id: 'run_1',
      status: 'processing',
      progress: 42,
      message: 'Section 3 wird generiert',
      message_key: 'report.generating',
      missing_sections: [],
      outline: { title: 'Report', summary: '—', sections: [] },
      sections: { '1': { content: 'eins' } },
      current_section_index: 1,
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('parses a Run-Registry payload without message_key ("incomplete"/"stopped" — Randzustand)', () => {
    const payload = {
      report_id: 'rep_1',
      status: 'incomplete',
      progress: 100,
      message: 'Report generated with degraded claims',
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(true)
  })

  it('rejects an unknown field (strict)', () => {
    const payload = {
      report_id: 'rep_1',
      status: 'completed',
      progress: 100,
      message: 'x',
      unexpected_field: true,
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(false)
  })

  it('rejects a message_key outside the four known values', () => {
    const payload = {
      report_id: 'rep_1',
      status: 'completed',
      progress: 100,
      message: 'x',
      message_key: 'report.unbekannt',
    }
    expect(ReportStatusResponseSchema.safeParse(payload).success).toBe(false)
  })
})
