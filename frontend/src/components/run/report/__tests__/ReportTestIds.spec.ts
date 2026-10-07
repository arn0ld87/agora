import { describe, expect, it, vi } from 'vitest'
import ReportEvidencePanel from '../evidence/ReportEvidencePanel.vue'
import ReportOutlinePane from '../ReportOutlinePane.vue'
import ReportReadingPane from '../ReportReadingPane.vue'
import { RunReportTestId } from '@/contracts/testIds'
import { claimsMap } from '@/composables/run/report/__tests__/claimFixtures'
import { mountWithReport, okApi } from './helpers'

/** Die Selektoren der e2e-Specs (`RunReportTestId`) müssen in den Komponenten ankommen. */
describe('RunReportTestId', () => {
  it('Gliederung, Eintrag je Abschnitt und Lesetext tragen die Kennungen des Vertrags', async () => {
    const outline = await mountWithReport(ReportOutlinePane, { activeSection: null })
    expect(outline.wrapper.find(`[data-testid="${RunReportTestId.outline}"]`).exists()).toBe(true)
    const items = outline.wrapper.findAll(`[data-testid^="${RunReportTestId.outlineItemPrefix}"]`)
    expect(items.map((i) => i.text()).join(' ')).toContain('Risiken')

    const reading = await mountWithReport(ReportReadingPane, { activeSection: null })
    const text = reading.wrapper.get(`[data-testid="${RunReportTestId.text}"]`)
    expect(text.text()).toContain('Ganzer Text.')
  })

  it('Belegspalte und Claims tragen die Kennungen des Vertrags', async () => {
    const api = okApi({ getReportEvidence: vi.fn().mockResolvedValue({ success: true, data: claimsMap() }) })
    const { wrapper } = await mountWithReport(
      ReportEvidencePanel,
      {
        simulationId: 'sim_1',
        artifactsApi: {
          getDensity: vi.fn().mockResolvedValue({ success: false, code: 'not_found' }),
          getStance: vi.fn().mockResolvedValue({ success: false, code: 'not_found' }),
        },
      },
      { api },
    )
    expect(wrapper.find(`[data-testid="${RunReportTestId.evidencePanel}"]`).exists()).toBe(true)
    expect(wrapper.findAll(`[data-testid="${RunReportTestId.claim}"]`)).toHaveLength(3)
  })
})
