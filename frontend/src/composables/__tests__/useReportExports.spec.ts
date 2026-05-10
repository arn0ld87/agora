import { describe, expect, it } from 'vitest'
import { buildStandaloneHtml } from '../useReportExports'

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
