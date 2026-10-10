import { describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { ApiError } from '@/api/envelope'
import ReportSidePane from '../ReportSidePane.vue'
import ReportOutlinePane from '../ReportOutlinePane.vue'
import ReportReadingPane from '../ReportReadingPane.vue'
import { listEnvelope, reportData } from '@/composables/run/report/__tests__/reportFixtures'
import { mountWithReport, okApi } from './helpers'

describe('ReportSidePane', () => {
  it('Tabs mit ARIA; Pfeiltasten, Pos1 und Ende schalten um und setzen den Fokus', async () => {
    const { wrapper } = await mountWithReport(ReportSidePane, { panel: 'evidence' })
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.map((t) => t.text())).toEqual(['Belege', 'Nachfragen'])
    expect(tabs[0]!.attributes('aria-selected')).toBe('true')
    expect(tabs[0]!.attributes('tabindex')).toBe('0')
    expect(tabs[1]!.attributes('tabindex')).toBe('-1')
    expect(tabs[0]!.attributes('aria-controls')).toBe('report-side-panel-evidence')
    expect(wrapper.get('[role="tablist"]').attributes('aria-label')).toBeTruthy()
    await tabs[0]!.trigger('keydown', { key: 'ArrowRight' })
    const side = wrapper.findComponent(ReportSidePane)
    expect(side.emitted('update:panel')?.[0]).toEqual(['questions'])
    await tabs[0]!.trigger('keydown', { key: 'ArrowLeft' })
    expect(side.emitted('update:panel')?.[1]).toEqual(['questions'])
    await tabs[0]!.trigger('keydown', { key: 'End' })
    expect(side.emitted('update:panel')?.[2]).toEqual(['questions'])
    await tabs[1]!.trigger('click')
    expect(side.emitted('update:panel')).toHaveLength(4)
  })

  it('zeigt je Tab einen Platzhalter und blendet den anderen Bereich aus', async () => {
    const { wrapper } = await mountWithReport(ReportSidePane, { panel: 'questions' })
    expect(wrapper.get('[data-testid="report-side-questions"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="report-side-evidence"]').isVisible()).toBe(false)
    expect(wrapper.find('[data-testid="report-questions-placeholder"]').exists()).toBe(true)
  })

  it('evidence_omitted: eigener, sichtbarer Hinweis im Bereich Belege, nie als Datenlücke formuliert', async () => {
    const omission = { reason: 'contract_violation', detail: 'x', validation_errors: ['Feld fehlt'] }
    const api = okApi({ getReportEvidence: vi.fn().mockResolvedValue({ success: true, evidence_omitted: omission }) })
    const { wrapper } = await mountWithReport(ReportSidePane, { panel: 'evidence' }, { api })
    const note = wrapper.get('[data-testid="report-evidence-omitted"]')
    expect(note.attributes('role')).toBe('alert')
    expect(note.text()).toContain('Belege ausgelassen (evidence_omitted)')
    expect(note.text()).toContain('Feld fehlt')
    expect(note.text()).toContain('keine Datenlücke')
    expect(wrapper.get('[data-testid="report-side-evidence"]').element.contains(note.element)).toBe(true)
  })

  it('Belege nicht ladbar: Fehler mit Grund', async () => {
    const api = okApi({ getReportEvidence: vi.fn().mockRejectedValue(new Error('offline')) })
    const { wrapper } = await mountWithReport(ReportSidePane, { panel: 'evidence' }, { api })
    expect(wrapper.get('[data-testid="report-evidence-failed"]').text()).toContain('offline')
  })

  it('UAT-010: Belege nicht gespeichert (404) sind ein sichtbarer Hinweis, kein Ladefehler', async () => {
    const api = okApi({
      getReportEvidence: vi
        .fn()
        .mockRejectedValue(new ApiError({ code: 'unknown_error', status: 404, message: 'No evidence map available for report: report_1' })),
    })
    const { wrapper } = await mountWithReport(ReportSidePane, { panel: 'evidence' }, { api })
    const note = wrapper.get('[data-testid="report-evidence-unsaved"]')
    expect(note.text()).toBe('Für diese Fassung sind keine Belege gespeichert.')
    expect(note.attributes('role')).toBeUndefined()
    expect(wrapper.find('[data-testid="report-evidence-failed"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('No evidence map available')
    expect(wrapper.get('[data-testid="report-side-evidence"]').element.contains(note.element)).toBe(true)
  })
})

describe('ReportOutlinePane', () => {
  it('Zustand je Abschnitt als Text: fertig, fehlt (missing_sections), fehlgeschlagen (generation_failed)', async () => {
    const rep = reportData({ status: 'incomplete', missing_sections: ['Akteure', 'Szenarien'] })
    const api = okApi({
      listReports: vi.fn().mockResolvedValue(listEnvelope([rep])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: rep }),
    })
    const { wrapper, ctx } = await mountWithReport(ReportOutlinePane, { activeSection: 1 }, { api })
    const items = wrapper.findAll('[data-testid^="report-outline-item-"]')
    expect(items.map((i) => i.attributes('data-state'))).toEqual(['ready', 'missing', 'missing'])
    expect(items[0]!.text()).toContain('fertig')
    expect(items[1]!.text()).toContain('fehlt')
    expect(items[2]!.text()).toContain('Szenarien')
    expect(items[0]!.attributes('aria-current')).toBe('location')
    ctx.generation.progress.sections.value = { '1': { content: 'x', generation_failed: true } }
    await flushPromises()
    expect(wrapper.get('[data-testid="report-outline-item-1"]').text()).toContain('fehlgeschlagen')
  })

  it('Sprung meldet den Abschnitt', async () => {
    const { wrapper } = await mountWithReport(ReportOutlinePane, { activeSection: null })
    await wrapper.get('[data-testid="report-outline-item-2"]').trigger('click')
    expect(wrapper.findComponent(ReportOutlinePane).emitted('select')?.[0]).toEqual([2])
  })
})

describe('ReportReadingPane', () => {
  it('sanitisiert den Lesetext (DOMPurify): kein Skript, kein Event-Handler', async () => {
    const rep = reportData({ markdown_content: 'Hallo <script>alert(1)</script><img src=x onerror=alert(1)> **fett**' })
    const api = okApi({
      listReports: vi.fn().mockResolvedValue(listEnvelope([rep])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: rep }),
    })
    const { wrapper } = await mountWithReport(ReportReadingPane, { activeSection: null }, { api })
    const html = wrapper.get('[data-testid="report-whole"]').html()
    expect(html).not.toContain('<script')
    expect(html).not.toContain('onerror')
    expect(html).toContain('<strong>fett</strong>')
  })

  it('Start wird nur auf Bestätigung angeboten (Sentinel new, kein Bericht)', async () => {
    const api = okApi({ listReports: vi.fn().mockResolvedValue(listEnvelope([])) })
    const { wrapper, generationApi } = await mountWithReport(ReportReadingPane, { activeSection: null }, { api, reportId: 'new' })
    expect(wrapper.find('[data-testid="report-start"]').exists()).toBe(true)
    expect(generationApi.generateReport).not.toHaveBeenCalled()
  })

  it('laufende Erzeugung: Fortschritt, fertige Abschnitte und einklappbares Protokoll', async () => {
    const running = reportData({ status: 'generating', completed_at: null })
    const api = okApi({
      listReports: vi.fn().mockResolvedValue(listEnvelope([running])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: running }),
    })
    const { wrapper, ctx } = await mountWithReport(ReportReadingPane, { activeSection: null }, { api })
    ctx.generation.progress.sections.value = { '1': { content: 'Erster Text', generation_failed: false } }
    await flushPromises()
    expect(wrapper.get('[data-testid="report-progress"]').text()).toContain('1 von 2 Abschnitten fertig')
    expect(wrapper.findAll('[data-testid="report-section"]')[0]!.text()).toContain('Erster Text')
    expect(wrapper.findAll('[data-testid="report-section"]')[1]!.attributes('data-state')).toBe('pending')
    const log = wrapper.get('details[data-testid="report-log"]')
    expect(log.get('summary').text()).toBe('Protokoll der Erzeugung')
    ctx.generation.stop()
  })

  it('fehlgeschlagener Bericht: Grund sichtbar', async () => {
    const failed = reportData({ status: 'failed', error: 'Budget erschöpft', completed_at: null })
    const api = okApi({
      listReports: vi.fn().mockResolvedValue(listEnvelope([failed])),
      getReport: vi.fn().mockResolvedValue({ success: true, data: failed }),
    })
    const { wrapper } = await mountWithReport(ReportReadingPane, { activeSection: null }, { api })
    expect(wrapper.get('[data-testid="report-failed"]').text()).toContain('Budget erschöpft')
  })
})
