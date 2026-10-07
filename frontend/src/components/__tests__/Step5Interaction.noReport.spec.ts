/**
 * Step5Interaction ohne reportId (Etappe 2, #1797): Uebergangsadresse
 * /v4/simulation/:simulationId/interviews. Ohne Bericht wird kein Bericht
 * geladen, die Ansicht oeffnet im Interview-Teil (Umfrage) und der Chat mit
 * dem Berichtsagenten ist ausgeblendet.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
  createI18n: () => ({ install: vi.fn() }),
}))

const getReport = vi.hoisted(() => vi.fn().mockResolvedValue({ success: false }))
const chatWithReport = vi.hoisted(() => vi.fn().mockResolvedValue({ success: false }))
vi.mock('../../api/report', () => ({ getReport, chatWithReport }))

const getSimulationProfilesRealtime = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ success: true, data: { profiles: [{ username: 'ada', bio: 'b' }] } }),
)
vi.mock('../../api/simulation', () => ({
  interviewAgents: vi.fn().mockResolvedValue({ success: false }),
  getSimulationProfilesRealtime,
}))

import Step5Interaction from '../Step5Interaction.vue'

describe('Step5Interaction ohne reportId', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('lädt keinen Bericht, lädt aber die Profile der Simulation', async () => {
    mount(Step5Interaction, { props: { simulationId: 'sim_abc' } })
    await flushPromises()
    expect(getReport).not.toHaveBeenCalled()
    expect(getSimulationProfilesRealtime).toHaveBeenCalledWith('sim_abc', 'reddit')
  })

  it('öffnet im Interview-Teil (Umfrage), nicht im Chat', async () => {
    const wrapper = mount(Step5Interaction, { props: { simulationId: 'sim_abc' } })
    await flushPromises()
    const tabs = wrapper.findAll('nav.tabs .tab')
    expect(tabs[1]?.classes()).toContain('active')
    expect(wrapper.text()).toContain('step5.survey.selectAll')
  })

  it('blendet den Berichtsagenten im Chat aus und sendet nie an ihn', async () => {
    const wrapper = mount(Step5Interaction, { props: { simulationId: 'sim_abc' } })
    await flushPromises()
    await wrapper.findAll('nav.tabs .tab')[0]!.trigger('click')
    expect(wrapper.text()).not.toContain('step5.selectReport')
    expect(wrapper.text()).not.toContain('ReportAgent')
    await wrapper.find('textarea').setValue('Hallo')
    await wrapper.find('.composer button').trigger('click')
    await flushPromises()
    expect(chatWithReport).not.toHaveBeenCalled()
  })

  it('mit reportId bleibt der Chat mit dem Berichtsagenten Standard', async () => {
    getReport.mockResolvedValueOnce({ success: true, data: { simulation_id: 'sim_abc' } })
    const wrapper = mount(Step5Interaction, { props: { reportId: 'report_abc' } })
    await flushPromises()
    expect(getReport).toHaveBeenCalledWith('report_abc')
    expect(wrapper.findAll('nav.tabs .tab')[0]?.classes()).toContain('active')
    expect(wrapper.text()).toContain('step5.selectReport')
  })
})
