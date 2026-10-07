import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  exportReport: vi.fn(),
  fetchReportCsv: vi.fn(),
  fetchReportBundle: vi.fn(),
}))
const download = vi.hoisted(() => vi.fn())

vi.mock('@/api/report', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }))
vi.mock('@/composables/useReportExports', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  triggerDownload: download,
}))

import ReportExportMenu from '../ReportExportMenu.vue'
import { listEnvelope, reportData } from '@/composables/run/report/__tests__/reportFixtures'
import { mountWithReport, okApi } from './helpers'

function blobOf(text: string): Blob {
  return { text: async () => text } as unknown as Blob
}

async function mountMenu(reportOver: Record<string, unknown> = {}, apiOver: Record<string, unknown> = {}) {
  const rep = reportData(reportOver)
  const res = await mountWithReport(
    ReportExportMenu,
    {},
    {
      api: okApi({
        listReports: vi.fn().mockResolvedValue(listEnvelope([rep])),
        getReport: vi.fn().mockResolvedValue({ success: true, data: rep }),
        ...apiOver,
      }),
    },
  )
  return res
}

async function openMenu(wrapper: { get: (s: string) => { trigger: (e: string, o?: object) => Promise<void> } }) {
  await wrapper.get('[data-testid="report-export-trigger"]').trigger('keydown', { key: 'ArrowDown' })
  await flushPromises()
}

const item = (action: string) => document.querySelector(`[data-testid="report-export-${action}"]`) as HTMLElement | null

describe('ReportExportMenu', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('bietet alle Formate des Bestands plus Drucken an; Trigger trägt aria-haspopup', async () => {
    const { wrapper } = await mountMenu()
    const trigger = wrapper.get('[data-testid="report-export-trigger"]')
    expect(trigger.attributes('aria-haspopup')).toBe('menu')
    await openMenu(wrapper)
    expect(document.querySelector('[role="menu"]')).not.toBeNull()
    const labels = Array.from(document.querySelectorAll('[role="menuitem"]')).map((e) => e.textContent?.trim())
    expect(labels).toEqual([
      'Markdown (.md)',
      'Markdown kopieren',
      'HTML (.html)',
      'JSON (.json)',
      'Belege (JSON)',
      'CSV: Personas',
      'CSV: Segmente',
      'CSV: Claims',
      'ZIP-Bündel (alle Dateien)',
      'Drucken',
    ])
    wrapper.unmount()
  })

  it('Markdown: ruft exportReport mit der gewählten Fassung auf, Dateiname wie im Bestand', async () => {
    api.exportReport.mockResolvedValue(blobOf('# md'))
    const { wrapper } = await mountMenu()
    await openMenu(wrapper)
    item('md')!.click()
    await flushPromises()
    expect(api.exportReport).toHaveBeenCalledWith('report_1', 'md')
    expect(download).toHaveBeenCalledWith(expect.anything(), 'agora-report-report_1.md')
    expect(wrapper.get('[data-testid="report-export-status"]').text()).toContain('fertig')
    wrapper.unmount()
  })

  it('wählt man eine andere Fassung, gilt der Export dieser Fassung', async () => {
    api.fetchReportBundle.mockResolvedValue(blobOf('zip'))
    const older = reportData({ report_id: 'report_0' })
    const { wrapper } = await mountMenu(
      {},
      {
        listReports: vi.fn().mockResolvedValue(listEnvelope([older, reportData()])),
        getReport: vi.fn(async (id: string) => ({ success: true, data: id === 'report_0' ? older : reportData() })),
      },
    )
    // jüngste Fassung ist gewählt
    await openMenu(wrapper)
    item('zip')!.click()
    await flushPromises()
    expect(api.fetchReportBundle).toHaveBeenCalledWith('report_1')
    expect(download).toHaveBeenCalledWith(expect.anything(), 'agora-report-report_1-bundle.zip')
    wrapper.unmount()
  })

  it('CSV und HTML nutzen die Dateinamen des Bestands', async () => {
    api.fetchReportCsv.mockResolvedValue(blobOf('a,b'))
    const { wrapper } = await mountMenu()
    await openMenu(wrapper)
    item('csv-claims')!.click()
    await flushPromises()
    expect(api.fetchReportCsv).toHaveBeenCalledWith('report_1', 'claims')
    expect(download).toHaveBeenCalledWith(expect.anything(), 'agora-report-report_1-claims.csv')
    await openMenu(wrapper)
    item('html')!.click()
    await flushPromises()
    expect(download).toHaveBeenLastCalledWith(expect.anything(), 'agora-report-report_1.html')
    wrapper.unmount()
  })

  it('Fehlerfall: Meldung mit Grund als role="alert", kein Download', async () => {
    api.fetchReportBundle.mockRejectedValue(new Error('Server nicht erreichbar'))
    const { wrapper } = await mountMenu()
    await openMenu(wrapper)
    item('zip')!.click()
    await flushPromises()
    const alert = wrapper.get('[data-testid="report-export-problem"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('fehlgeschlagen')
    expect(alert.text()).toContain('Server nicht erreichbar')
    expect(download).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('JSON mit evidence_omitted: Datei kommt, aber eine sichtbare Warnung bleibt', async () => {
    const envelope = {
      schema_version: 2,
      exported_at: '2026-10-07T10:00:00Z',
      report: reportData(),
      evidence: null,
      evidence_omitted: { reason: 'contract_violation', detail: 'Evidence verletzt den Vertrag', validation_errors: ['x'] },
    }
    api.exportReport.mockResolvedValue(blobOf(JSON.stringify(envelope)))
    const { wrapper } = await mountMenu()
    await openMenu(wrapper)
    item('json')!.click()
    await flushPromises()
    expect(download).toHaveBeenCalledWith(expect.anything(), 'agora-report-report_1.json')
    expect(wrapper.get('[data-testid="report-export-problem"]').text()).toContain('evidence_omitted')
    wrapper.unmount()
  })

  it('Vertragsverletzung im JSON-Export ist ein Fehler, kein Download', async () => {
    api.exportReport.mockResolvedValue(blobOf(JSON.stringify({ schema_version: 1 })))
    const { wrapper } = await mountMenu()
    await openMenu(wrapper)
    item('json')!.click()
    await flushPromises()
    expect(wrapper.get('[data-testid="report-export-problem"]').text()).toContain('fehlgeschlagen')
    expect(download).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('gesperrt ohne Fassung und während der Erzeugung, mit Erklärung; kein Menü', async () => {
    const running = await mountMenu({ status: 'generating', completed_at: null })
    const trigger = running.wrapper.get('[data-testid="report-export-trigger"]')
    expect(trigger.attributes('aria-disabled')).toBe('true')
    expect(trigger.attributes('aria-describedby')).toBe('report-export-blocked')
    expect(running.wrapper.get('[data-testid="report-export-blocked"]').text()).toContain('noch erzeugt')
    await trigger.trigger('click')
    await openMenu(running.wrapper)
    expect(document.querySelector('[role="menu"]')).toBeNull()
    running.wrapper.unmount()

    const none = await mountWithReport(ReportExportMenu, {}, { api: okApi({ listReports: vi.fn().mockResolvedValue(listEnvelope([])) }) })
    expect(none.wrapper.get('[data-testid="report-export-blocked"]').text()).toContain('keine Fassung')
    none.wrapper.unmount()
  })

  it('unvollständige Fassung bleibt exportierbar, das Menü sagt es dazu', async () => {
    api.fetchReportBundle.mockResolvedValue(blobOf('zip'))
    const { wrapper } = await mountMenu({ status: 'incomplete', missing_sections: ['Akteure'] })
    await openMenu(wrapper)
    expect(document.querySelector('[data-testid="report-export-incomplete"]')?.textContent).toContain(
      'Diese Fassung ist unvollständig',
    )
    item('zip')!.click()
    await flushPromises()
    expect(api.fetchReportBundle).toHaveBeenCalledWith('report_1')
    wrapper.unmount()
  })

  it('Drucken ruft window.print auf; die Kopfzeile des Drucks nennt Titel, Fassung und Zustand', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    const { wrapper } = await mountMenu()
    const head = wrapper.get('[data-testid="report-print-head"]').text()
    expect(head).toContain('Bericht: Branche und Abgabe')
    expect(head).toContain('Fassung 1')
    expect(head).toContain('Fertig')
    await openMenu(wrapper)
    item('print')!.click()
    await flushPromises()
    expect(print).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('Tastatur: Pfeil unten öffnet, Enter auf einem Eintrag führt ihn aus, Escape schließt', async () => {
    api.fetchReportCsv.mockResolvedValue(blobOf('a'))
    const { wrapper } = await mountMenu()
    await openMenu(wrapper)
    const personas = item('csv-personas')!
    personas.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await flushPromises()
    expect(api.fetchReportCsv).toHaveBeenCalledWith('report_1', 'personas')

    await openMenu(wrapper)
    expect(document.querySelector('[role="menu"]')).not.toBeNull()
    document
      .querySelector('[role="menu"]')!
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role="menu"]')).toBeNull()
    wrapper.unmount()
  })
})
