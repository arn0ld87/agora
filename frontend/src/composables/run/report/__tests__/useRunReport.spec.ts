import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { ApiError } from '@/api/envelope'
import {
  parseVersions,
  provideRunReport,
  useRunReport,
  useRunReportContext,
  type RunReportContext,
} from '../useRunReport'
import { evidenceMap, listEnvelope, reportData } from './reportFixtures'

function setup(opts: { reportId?: string; api: Record<string, unknown>; onStarted?: (id: string) => void }) {
  const routed = ref<string | undefined>(opts.reportId)
  let ctx!: RunReportContext
  const generationApi = {
    getReportStatus: vi.fn().mockResolvedValue({ success: false }),
    getReport: vi.fn().mockResolvedValue({ success: false }),
    generateReport: vi.fn(),
  }
  const wrapper = mount(
    defineComponent({
      setup() {
        ctx = useRunReport({
          simulationId: () => 'sim_1',
          reportId: () => routed.value,
          t: (k) => k,
          onStarted: opts.onStarted,
          api: opts.api as never,
          generationApi: generationApi as never,
        })
        return () => h('div')
      },
    }),
  )
  return { ctx, routed, generationApi, wrapper }
}

const completed = reportData()
const older = reportData({ report_id: 'report_0', created_at: '2026-10-01T00:00:00Z', completed_at: '2026-10-01T00:30:00Z' })

function okApi(over: Record<string, unknown> = {}) {
  return {
    listReports: vi.fn().mockResolvedValue(listEnvelope([older, completed])),
    getReport: vi.fn(async (id: string) => ({ success: true, data: id === 'report_0' ? older : completed })),
    getReportEvidence: vi.fn(async (id: string) => ({ success: true, data: evidenceMap(id) })),
    ...over,
  }
}

describe('parseVersions', () => {
  it('nummeriert vom ältesten aufwärts, neueste zuerst, und zählt Vertragsverletzer', () => {
    const state = parseVersions(listEnvelope([older, completed, { report_id: 'kaputt' }]))
    expect(state).toMatchObject({ status: 'ok', invalid: 1 })
    if (state.status !== 'ok') throw new Error('unreachable')
    expect(state.items.map((v) => [v.reportId, v.number, v.status])).toEqual([
      ['report_1', 2, 'completed'],
      ['report_0', 1, 'completed'],
    ])
  })

  it('Fehlerumschlag und Vertragsbruch der Hülle sind failed', () => {
    expect(parseVersions({ success: false, error: 'kaputt' })).toEqual({ status: 'failed', reason: 'kaputt' })
    expect(parseVersions('quatsch').status).toBe('failed')
  })
})

describe('useRunReport', () => {
  it('ok: lädt Fassungen, wählt ohne Adresse die jüngste, lädt Bericht und Belege', async () => {
    const api = okApi()
    const { ctx } = setup({ api })
    expect(ctx.versions.value.status).toBe('loading')
    await ctx.reload()
    expect(ctx.versions.value.status).toBe('ok')
    expect(ctx.selectedReportId.value).toBe('report_1')
    expect(ctx.report.value).toMatchObject({ status: 'ok' })
    expect(ctx.evidence.value.status).toBe('ok')
    expect(api.getReport).toHaveBeenCalledWith('report_1')
    expect(api.getReportEvidence).toHaveBeenCalledWith('report_1')
    expect(ctx.outline.value.map((e) => [e.title, e.state])).toEqual([
      ['Risiken', 'ready'],
      ['Akteure', 'ready'],
    ])
  })

  it('omitted: evidence_omitted bleibt ein eigener Zustand mit Begründung, nie ok', async () => {
    const omission = { reason: 'contract_violation' as const, detail: 'Beleg verletzt Vertrag', validation_errors: ['a'] }
    const api = okApi({ getReportEvidence: vi.fn().mockResolvedValue({ success: true, evidence_omitted: omission }) })
    const { ctx } = setup({ api })
    await ctx.reload()
    expect(ctx.evidence.value).toEqual({ status: 'omitted', omission })
    expect(ctx.report.value.status).toBe('ok')
  })

  it('failed: Belege nicht ladbar (Transport) und Schema-Mismatch sind unterscheidbar', async () => {
    const down = okApi({ getReportEvidence: vi.fn().mockRejectedValue(new ApiError({ code: 'http_500', status: 500, message: 'boom' })) })
    const a = setup({ api: down })
    await a.ctx.reload()
    expect(a.ctx.evidence.value).toMatchObject({ status: 'failed', kind: 'transport', reason: 'boom' })

    const drift = okApi({
      getReportEvidence: vi.fn().mockRejectedValue(new ApiError({ code: 'schema_mismatch', status: 0, message: 'schema mismatch: x' })),
    })
    const b = setup({ api: drift })
    await b.ctx.reload()
    expect(b.ctx.evidence.value).toMatchObject({ status: 'failed', kind: 'contract' })
  })

  it('Zod-Verletzung des Berichts wird sichtbar (failed/contract), nicht tolerant weitergerendert', async () => {
    const api = okApi({ getReport: vi.fn().mockResolvedValue({ success: true, data: { report_id: 'report_1' } }) })
    const { ctx } = setup({ api })
    await ctx.reload()
    expect(ctx.report.value).toMatchObject({ status: 'failed', kind: 'contract' })
    expect((ctx.report.value as { reason: string }).reason).toContain('Vertragsbruch GET /api/report/report_1')
    expect(ctx.evidence.value.status).toBe('idle')
    expect(ctx.outline.value).toEqual([])
  })

  it('Zod-Verletzung der Fassungsliste: ungültige Fassungen werden gezählt, die Liste als Ganzes bei kaputter Hülle failed', async () => {
    const api = okApi({ listReports: vi.fn().mockResolvedValue({ success: true, data: 'kein array' }) })
    const { ctx } = setup({ api })
    await ctx.reload()
    expect(ctx.versions.value.status).toBe('failed')
  })

  it('404 des Berichts: failed/notFound', async () => {
    const api = okApi({ getReport: vi.fn().mockRejectedValue(new ApiError({ code: 'not_found', status: 404, message: 'weg' })) })
    const { ctx } = setup({ api, reportId: 'report_x' })
    await ctx.reload()
    expect(ctx.report.value).toMatchObject({ status: 'failed', kind: 'notFound' })
  })

  it('UAT-010: 404 der Belege einer geladenen Fassung ist unsaved, kein Ladefehler', async () => {
    const incomplete = reportData({
      status: 'incomplete',
      missing_sections: ['Persona-Mindestanzahl nicht erreicht: 18/20 Personas vorhanden.'],
    })
    const base = {
      listReports: vi.fn().mockResolvedValue(listEnvelope([incomplete])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: incomplete }),
    }
    const a = setup({
      api: okApi({
        ...base,
        getReportEvidence: vi
          .fn()
          .mockRejectedValue(new ApiError({ code: 'unknown_error', status: 404, message: 'No evidence map available for report: report_1' })),
      }),
    })
    await a.ctx.reload()
    expect(a.ctx.report.value.status).toBe('ok')
    expect(a.ctx.evidence.value).toEqual({ status: 'unsaved' })

    const b = setup({
      api: okApi({
        ...base,
        getReportEvidence: vi.fn().mockResolvedValue({ success: false, code: 'not_found', error: 'weg' }),
      }),
    })
    await b.ctx.reload()
    expect(b.ctx.evidence.value).toEqual({ status: 'unsaved' })
  })

  it('Fassungswechsel über die Adresse lädt nur Bericht und Belege der neuen Fassung', async () => {
    const api = okApi()
    const { ctx, routed } = setup({ api, reportId: 'report_1' })
    await ctx.reload()
    expect(api.listReports).toHaveBeenCalledTimes(1)
    routed.value = 'report_0'
    await flushPromises()
    expect(ctx.selectedReportId.value).toBe('report_0')
    expect(api.getReport).toHaveBeenLastCalledWith('report_0')
    expect(api.getReportEvidence).toHaveBeenLastCalledWith('report_0')
    expect(api.listReports).toHaveBeenCalledTimes(1)
    expect(ctx.report.value).toMatchObject({ status: 'ok', report: { report_id: 'report_0' } })
  })

  it('läuft der Bericht noch, gibt es keine Belegabfrage; die Erzeugungsabfrage wird gestartet', async () => {
    const running = reportData({ status: 'generating', completed_at: null })
    const api = okApi({ getReport: vi.fn().mockResolvedValue({ success: true, data: running }) })
    const { ctx, generationApi } = setup({ api })
    await ctx.reload()
    expect(ctx.evidence.value.status).toBe('idle')
    expect(api.getReportEvidence).not.toHaveBeenCalled()
    expect(generationApi.getReportStatus).toHaveBeenCalled()
    ctx.generation.stop()
  })

  it('Sentinel new ohne Fassung: kein Bericht gewählt, Start wird angeboten (pending)', async () => {
    const api = okApi({ listReports: vi.fn().mockResolvedValue(listEnvelope([])) })
    const { ctx } = setup({ api, reportId: 'new' })
    await ctx.reload()
    expect(ctx.selectedReportId.value).toBeNull()
    expect(ctx.report.value.status).toBe('idle')
    expect(ctx.generation.status.pending.value).toBe(true)
    ctx.generation.stop()
  })

  it('selectClaim setzt und löscht die Auswahl', async () => {
    const { ctx } = setup({ api: okApi() })
    ctx.selectClaim('claim_7')
    expect(ctx.selectedClaimId.value).toBe('claim_7')
    ctx.selectClaim(null)
    expect(ctx.selectedClaimId.value).toBeNull()
  })

  it('useRunReportContext: mit Provider derselbe Kontext, ohne Provider ein ruhender Rückfall', () => {
    let provided!: RunReportContext
    let seen!: RunReportContext
    const Child = defineComponent({
      setup() {
        seen = useRunReportContext()
        return () => h('i')
      },
    })
    mount(
      defineComponent({
        setup() {
          provided = useRunReport({ simulationId: () => 'sim_1', reportId: () => undefined, t: (k) => k, api: okApi() as never })
          provideRunReport(provided)
          return () => h(Child)
        },
      }),
    )
    expect(seen).toBe(provided)

    let fallback!: RunReportContext
    mount(
      defineComponent({
        setup() {
          fallback = useRunReportContext()
          return () => h('i')
        },
      }),
    )
    expect(fallback.report.value.status).toBe('idle')
    expect(fallback.evidence.value.status).toBe('idle')
    expect(fallback.outline.value).toEqual([])
    expect(fallback.selectedReportId.value).toBeNull()
  })
})
