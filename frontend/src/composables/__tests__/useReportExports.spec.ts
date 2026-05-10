import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { exportReport } from '../../api/report'
import { buildStandaloneHtml, useReportExports } from '../useReportExports'

vi.mock('../../api/report', () => ({
  exportReport: vi.fn(),
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

describe('useReportExports', () => {
  it('lädt Markdown bevorzugt ueber den Server-Export', async () => {
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const anchor = document.createElement('a')
    const click = vi.spyOn(anchor, 'click').mockImplementation(() => undefined)
    const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue(anchor)
    vi.mocked(exportReport).mockResolvedValue(new Blob(['# ReportV3'], { type: 'text/markdown' }))

    const exportsApi = useReportExports({
      reportId: () => 'report_abcdef123456',
      reportMarkdown: computed(() => '# Legacy'),
      reportHtml: computed(() => '<h1>Legacy</h1>'),
      evidenceMap: ref(null),
      addLog: vi.fn(),
      recordSchemaError: vi.fn(),
    })

    await exportsApi.downloadMarkdown()

    expect(exportReport).toHaveBeenCalledWith('report_abcdef123456', 'md')
    expect(createObjectUrlSpy).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()

    createObjectUrlSpy.mockRestore()
    revokeSpy.mockRestore()
    createElementSpy.mockRestore()
    vi.restoreAllMocks()
  })
})
