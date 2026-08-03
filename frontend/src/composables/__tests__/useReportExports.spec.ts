import { computed, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { exportReport, fetchReportBundle, fetchReportCsv } from '../../api/report'
import { buildStandaloneHtml, useReportExports } from '../useReportExports'
import omittedEnvelope from './fixtures/report-export-envelope-evidence-omitted.json'

vi.mock('../../api/report', () => ({
  exportReport: vi.fn(),
  fetchReportBundle: vi.fn(),
  fetchReportCsv: vi.fn(),
}))

describe('buildStandaloneHtml', () => {
  it('enthält Print-Styles für Confidence-Badges', () => {
    const html = buildStandaloneHtml(
      'Report',
      '<span class="conf-badge conf-low">Low-Confidence-Hinweis</span>'
    )

    expect(html).toContain('.conf-badge')
    expect(html).toContain('.conf-low')
    expect(html).toContain('.conf-medium')
    expect(html).toContain('Low-Confidence-Hinweis')
  })
})

function makeExportsApi(addLog = vi.fn()) {
  return useReportExports({
    reportId: () => 'report_abcdef123456',
    reportMarkdown: computed(() => '# Legacy'),
    reportHtml: computed(() => '<h1>Legacy</h1>'),
    evidenceMap: ref(null),
    addLog,
    recordSchemaError: vi.fn(),
  })
}

describe('useReportExports', () => {
  let createObjectUrlSpy: ReturnType<typeof vi.spyOn>
  let revokeSpy: ReturnType<typeof vi.spyOn>
  let anchor: HTMLAnchorElement
  let click: ReturnType<typeof vi.spyOn>
  let createElementSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
    revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    anchor = document.createElement('a')
    click = vi.spyOn(anchor, 'click').mockImplementation(() => undefined)
    createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue(anchor)
  })

  afterEach(() => {
    createObjectUrlSpy.mockRestore()
    revokeSpy.mockRestore()
    createElementSpy.mockRestore()
    vi.restoreAllMocks()
  })

  it('lädt Markdown bevorzugt ueber den Server-Export', async () => {
    vi.mocked(exportReport).mockResolvedValue(new Blob(['# ReportV3'], { type: 'text/markdown' }))

    const exportsApi = makeExportsApi()
    await exportsApi.downloadMarkdown()

    expect(exportReport).toHaveBeenCalledWith('report_abcdef123456', 'md')
    expect(createObjectUrlSpy).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
  })

  it('downloadCsv ruft fetchReportCsv mit korrekter Tabelle auf', async () => {
    vi.mocked(fetchReportCsv).mockResolvedValue(
      new Blob(['id,beruf\nP1,Entwickler'], { type: 'text/csv' })
    )

    const exportsApi = makeExportsApi()
    await exportsApi.downloadCsv('personas')

    expect(fetchReportCsv).toHaveBeenCalledWith('report_abcdef123456', 'personas')
    expect(createObjectUrlSpy).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
  })

  it('downloadCsv setzt korrekten Dateinamen', async () => {
    vi.mocked(fetchReportCsv).mockResolvedValue(
      new Blob(['id,beruf\nP1,Entwickler'], { type: 'text/csv' })
    )

    const exportsApi = makeExportsApi()
    await exportsApi.downloadCsv('segments')

    expect(anchor.download).toBe('agora-report-report_abcdef123456-segments.csv')
  })

  it('downloadCsv nutzt optionalen Dateinamen', async () => {
    vi.mocked(fetchReportCsv).mockResolvedValue(
      new Blob(['id,beruf'], { type: 'text/csv' })
    )

    const exportsApi = makeExportsApi()
    await exportsApi.downloadCsv('claims', 'mein-export.csv')

    expect(anchor.download).toBe('mein-export.csv')
  })

  it('downloadCsv loggt Fehler bei fehlgeschlagenem Fetch', async () => {
    vi.mocked(fetchReportCsv).mockRejectedValue(new Error('Netzwerkfehler'))

    const addLog = vi.fn()
    const exportsApi = makeExportsApi(addLog)
    await exportsApi.downloadCsv('personas')

    expect(addLog).toHaveBeenCalledWith(
      expect.stringContaining('Netzwerkfehler')
    )
    expect(click).not.toHaveBeenCalled()
  })

  it('downloadCsvBundle lädt alle drei Tabellen', async () => {
    vi.mocked(fetchReportCsv).mockResolvedValue(
      new Blob(['a,b\n1,2'], { type: 'text/csv' })
    )

    const addLog = vi.fn()
    const exportsApi = makeExportsApi(addLog)
    await exportsApi.downloadCsvBundle()

    expect(fetchReportCsv).toHaveBeenCalledTimes(3)
    expect(fetchReportCsv).toHaveBeenCalledWith('report_abcdef123456', 'personas')
    expect(fetchReportCsv).toHaveBeenCalledWith('report_abcdef123456', 'segments')
    expect(fetchReportCsv).toHaveBeenCalledWith('report_abcdef123456', 'claims')
    expect(addLog).toHaveBeenCalledWith(expect.stringContaining('alle drei'))
  })

  it('downloadCsvBundle loggt Fehler bei partiellem Fehler', async () => {
    vi.mocked(fetchReportCsv)
      .mockResolvedValueOnce(new Blob(['a'], { type: 'text/csv' }))
      .mockRejectedValueOnce(new Error('Segment-Fehler'))
      .mockResolvedValueOnce(new Blob(['b'], { type: 'text/csv' }))

    const addLog = vi.fn()
    const exportsApi = makeExportsApi(addLog)
    await exportsApi.downloadCsvBundle()

    expect(addLog).toHaveBeenCalledWith(expect.stringContaining('Segment-Fehler'))
  })

  it('downloadAllBundle ruft /export?format=zip auf und triggert Download', async () => {
    vi.mocked(fetchReportBundle).mockResolvedValue(
      new Blob(['PK...'], { type: 'application/zip' })
    )

    const exportsApi = makeExportsApi()
    await exportsApi.downloadAllBundle()

    expect(fetchReportBundle).toHaveBeenCalledWith('report_abcdef123456')
    expect(createObjectUrlSpy).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(anchor.download).toBe('agora-report-report_abcdef123456-bundle.zip')
  })

  it('downloadAllBundle akzeptiert optionalen Dateinamen', async () => {
    vi.mocked(fetchReportBundle).mockResolvedValue(
      new Blob(['PK...'], { type: 'application/zip' })
    )

    const exportsApi = makeExportsApi()
    await exportsApi.downloadAllBundle('mein-bundle.zip')

    expect(anchor.download).toBe('mein-bundle.zip')
  })

  it('downloadAllBundle loggt Fehler bei fehlgeschlagenem Fetch', async () => {
    vi.mocked(fetchReportBundle).mockRejectedValue(new Error('Netzwerk-ZIP-Fehler'))

    const addLog = vi.fn()
    const exportsApi = makeExportsApi(addLog)
    await exportsApi.downloadAllBundle()

    expect(addLog).toHaveBeenCalledWith(expect.stringContaining('Netzwerk-ZIP-Fehler'))
    expect(click).not.toHaveBeenCalled()
  })
  // Issue #987 — Cross-Layer-Kette fuer den JSON-Export.
  //
  // Die Fixture ist kein handgebautes Objekt, sondern die woertliche Antwort
  // von GET /api/report/<id>/export?format=json, erzeugt vom echten
  // ReportExportService gegen eine Evidence-Map, die den Vertrag verletzt.
  // Damit belegt dieser Test die ganze Kette: Pydantic-Produzent -> HTTP ->
  // Zod-Spiegel -> Composable -> sichtbarer Log-Eintrag. Ein Zod-Schema, das
  // `evidence_omitted` nicht kennt, laesst den Test an `.strict()` scheitern.
  it('macht eine verworfene Evidence-Map im JSON-Export sichtbar', async () => {
    vi.mocked(exportReport).mockResolvedValue(
      new Blob([JSON.stringify(omittedEnvelope)], { type: 'application/json' })
    )

    const addLog = vi.fn()
    const exportsApi = makeExportsApi(addLog)
    await exportsApi.downloadCombinedJson()

    expect(addLog).toHaveBeenCalledWith(
      expect.stringContaining('Evidence fehlt in der Datei')
    )
    expect(addLog).toHaveBeenCalledWith(
      expect.stringContaining('Extra inputs are not permitted')
    )
    // Der Fallback bleibt: der Report-Rumpf wird weiterhin ausgeliefert.
    expect(click).toHaveBeenCalled()
  })

  it('meldet nichts, wenn der Envelope keine Auslassung traegt', async () => {
    const healthy = { ...omittedEnvelope, evidence_omitted: null }
    vi.mocked(exportReport).mockResolvedValue(
      new Blob([JSON.stringify(healthy)], { type: 'application/json' })
    )

    const addLog = vi.fn()
    const exportsApi = makeExportsApi(addLog)
    await exportsApi.downloadCombinedJson()

    expect(addLog).not.toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
  })
})
