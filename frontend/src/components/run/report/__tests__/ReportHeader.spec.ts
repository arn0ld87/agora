import { describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { flushPromises } from '@vue/test-utils'
import ReportHeader from '../ReportHeader.vue'
import { evidenceMap, listEnvelope, reportData } from '@/composables/run/report/__tests__/reportFixtures'
import { mountWithReport, okApi } from './helpers'

describe('ReportHeader', () => {
  it('Fassungswähler nennt jede Fassung mit Nummer, Datum und Zustand; die jüngste ist gewählt; ohne Beleg kein Modell', async () => {
    const { wrapper } = await mountWithReport(ReportHeader, { simulationId: 'sim_1' })
    const select = wrapper.get('[data-testid="report-version-select"]')
    const options = select.findAll('option').map((o) => o.text())
    expect(options).toHaveLength(2)
    expect(options[0]).toMatch(/^Fassung 2 · .+ · Fertig$/)
    expect(options[1]).toMatch(/^Fassung 1 · .+ · Fertig$/)
    expect((select.element as HTMLSelectElement).value).toBe('report_1')
    expect(wrapper.get('label[for="report-version-select"]').text()).toBe('Fassung')
    expect(wrapper.text()).not.toMatch(/Modell/)
  })

  it('nennt das Modell je Fassung, wenn der Bericht es belegt, sonst nichts', async () => {
    const withModel = reportData({
      report_id: 'report_1',
      llm_model: 'gpt-5.4',
      llm_provider_id: 'openai',
    })
    const without = reportData({ report_id: 'report_0', created_at: '2026-10-01T00:00:00Z', completed_at: '2026-10-01T00:30:00Z' })
    const api = okApi({
      listReports: vi.fn().mockResolvedValue(listEnvelope([without, withModel])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: withModel }),
    })
    const { wrapper } = await mountWithReport(ReportHeader, { simulationId: 'sim_1' }, { api })
    const options = wrapper.get('[data-testid="report-version-select"]').findAll('option').map((o) => o.text())
    expect(options[0]).toMatch(/^Fassung 2 · .+ · Fertig · gpt-5\.4$/)
    expect(options[1]).toMatch(/^Fassung 1 · .+ · Fertig$/)
  })

  it('zeigt den Zustand der gewählten Fassung als Text; Unvollständig ist nicht Fertig', async () => {
    const inc = reportData({ status: 'incomplete', missing_sections: ['Akteure'] })
    const api = okApi({
      listReports: vi.fn().mockResolvedValue(listEnvelope([inc])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: inc }),
    })
    const { wrapper } = await mountWithReport(ReportHeader, { simulationId: 'sim_1' }, { api })
    const state = wrapper.get('[data-testid="report-state"]')
    expect(state.text()).toContain('Unvollständig')
    expect(state.text()).not.toContain('Fertig')
    expect(state.get('[data-testid="run-state-mark"]').attributes('data-state')).toBe('incomplete')
  })

  it('der Wechsel der Fassung ändert die Adresse und behält ?panel=', async () => {
    const { wrapper, router } = await mountWithReport(
      ReportHeader,
      { simulationId: 'sim_1' },
      { route: '/simulations/sim_1/report/report_1?panel=questions&claim=c1&section=2' },
    )
    const select = wrapper.get('[data-testid="report-version-select"]')
    await select.setValue('report_0')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunReport')
    expect(router.currentRoute.value.params).toMatchObject({ simulationId: 'sim_1', reportId: 'report_0' })
    expect(router.currentRoute.value.query).toEqual({ panel: 'questions' })
  })

  it('nach „Neu erzeugen mit …“ (done) werden die Fassungen neu geladen und auf die neue gewechselt', async () => {
    const created = reportData({ report_id: 'report_2', created_at: '2026-10-07T00:00:00Z', completed_at: null, status: 'generating' })
    const base = okApi()
    const listReports = vi
      .fn()
      .mockResolvedValueOnce(listEnvelope([reportData({ report_id: 'report_0', created_at: '2026-10-01T00:00:00Z' }), reportData()]))
      .mockResolvedValue(listEnvelope([reportData({ report_id: 'report_0', created_at: '2026-10-01T00:00:00Z' }), reportData(), created]))
    const api = { ...base, listReports, getReport: vi.fn(async (id: string) => ({ success: true, data: id === 'report_2' ? created : reportData() })), getReportEvidence: vi.fn(async (id: string) => ({ success: true, data: evidenceMap(id) })) }
    const { wrapper, router } = await mountWithReport(ReportHeader, { simulationId: 'sim_1' }, { api, route: '/simulations/sim_1/report/report_1', reportId: 'report_1' })
    wrapper.findComponent({ name: 'RunReportRegenerate' }).vm.$emit('done')
    await flushPromises()
    expect(listReports).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.params).toMatchObject({ reportId: 'report_2' })
  })

  it('Slot actions steht für das Export-Menü bereit', async () => {
    const { wrapper } = await mountWithReport(
      ReportHeader,
      { simulationId: 'sim_1' },
      { slots: { actions: () => h('button', { 'data-testid': 'export-slot' }, 'Export') } },
    )
    expect(wrapper.get('[data-testid="export-slot"]').text()).toBe('Export')
  })

  it('ohne Fassung: Hinweis statt Auswahl; Ladefehler und Vertragsverletzer sind sichtbar', async () => {
    const none = await mountWithReport(ReportHeader, { simulationId: 'sim_1' }, { api: okApi({ listReports: vi.fn().mockResolvedValue(listEnvelope([])) }) })
    expect(none.wrapper.find('[data-testid="report-version-select"]').exists()).toBe(false)
    expect(none.wrapper.get('[data-testid="report-versions-none"]').text()).toBe('Noch keine Fassung')

    const failed = await mountWithReport(ReportHeader, { simulationId: 'sim_1' }, { api: okApi({ listReports: vi.fn().mockRejectedValue(new Error('offline')) }) })
    expect(failed.wrapper.get('[data-testid="report-versions-failed"]').attributes('role')).toBe('alert')
    expect(failed.wrapper.get('[data-testid="report-versions-failed"]').text()).toContain('offline')

    const invalid = await mountWithReport(
      ReportHeader,
      { simulationId: 'sim_1' },
      { api: okApi({ listReports: vi.fn().mockResolvedValue(listEnvelope([reportData(), { report_id: 'kaputt' }])) }) },
    )
    expect(invalid.wrapper.get('[data-testid="report-versions-invalid"]').text()).toContain('1 Fassung verletzt den Vertrag')
  })
})
