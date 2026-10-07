import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { ApiError } from '@/api/envelope'
import { reportData } from '@/composables/run/report/__tests__/reportFixtures'
import ReportRedirectView from '../ReportRedirectView.vue'

const api = vi.hoisted(() => ({ getReport: vi.fn() }))
vi.mock('@/api/report', () => ({ getReport: api.getReport }))

const Stub = defineComponent({ render: () => h('div') })

async function mountAt(path: string, panel?: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/v4/report/:reportId', name: 'StepReport', component: ReportRedirectView, props: true },
      { path: '/simulations/:simulationId/report/:reportId?', name: 'RunReport', component: Stub },
      { path: '/library/runs', name: 'LibraryRuns', component: Stub },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(
    defineComponent({ render: () => h(ReportRedirectView, { reportId: String(router.currentRoute.value.params.reportId), panel }) }),
    { global: { plugins: [router, createI18n({ legacy: false, locale: 'de', messages: { de } as never })] } },
  )
  await flushPromises()
  return { router, wrapper }
}

beforeEach(() => vi.clearAllMocks())

describe('ReportRedirectView', () => {
  it('löst die Simulation über getReport auf; Query und Hash bleiben', async () => {
    api.getReport.mockResolvedValue({ success: true, data: reportData({ report_id: 'report_9', simulation_id: 'sim_7' }) })
    const { router } = await mountAt('/v4/report/report_9?claim=c1#x')
    expect(api.getReport).toHaveBeenCalledWith('report_9')
    expect(router.currentRoute.value.fullPath).toBe('/simulations/sim_7/report/report_9?claim=c1#x')
  })

  it('?simId= wird genutzt und nicht in die neue Adresse übernommen; kein Abruf nötig', async () => {
    const { router } = await mountAt('/v4/report/report_9?simId=sim_3&panel=questions')
    expect(api.getReport).not.toHaveBeenCalled()
    expect(router.currentRoute.value.fullPath).toBe('/simulations/sim_3/report/report_9?panel=questions')
  })

  it('mit panel (alte Adresse /v4/interaction/:reportId, #1790) zielt die Weiterleitung auf ?panel=questions', async () => {
    api.getReport.mockResolvedValue({ success: true, data: reportData({ report_id: 'report_9', simulation_id: 'sim_7' }) })
    const { router } = await mountAt('/v4/report/report_9?claim=c1#x', 'questions')
    expect(router.currentRoute.value.fullPath).toBe('/simulations/sim_7/report/report_9?claim=c1&panel=questions#x')
  })

  it('ein vorhandenes ?panel= gewinnt gegen den Vorgabewert', async () => {
    const { router } = await mountAt('/v4/report/report_9?simId=sim_3&panel=evidence', 'questions')
    expect(router.currentRoute.value.fullPath).toBe('/simulations/sim_3/report/report_9?panel=evidence')
  })

  it('eine Registry-Run-ID (run_…) in ?simId= wird nie als Simulation genutzt (#1023), die Simulation kommt aus dem Bericht', async () => {
    api.getReport.mockResolvedValue({ success: true, data: reportData({ report_id: 'report_9', simulation_id: 'sim_7' }) })
    const { router } = await mountAt('/v4/report/report_9?simId=run_a1b2c3d4e5f6', 'questions')
    expect(api.getReport).toHaveBeenCalledWith('report_9')
    expect(router.currentRoute.value.fullPath).toContain('/simulations/sim_7/report/report_9')
  })

  it('Sentinel new mit ?simulationId=', async () => {
    const { router } = await mountAt('/v4/report/new?simulationId=sim_4&runId=run_a')
    expect(router.currentRoute.value.fullPath).toBe('/simulations/sim_4/report/new?runId=run_a')
  })

  it('404: „Bericht nicht gefunden“ ohne Weiterleitung', async () => {
    api.getReport.mockRejectedValue(new ApiError({ code: 'not_found', status: 404, message: 'weg' }))
    const { router, wrapper } = await mountAt('/v4/report/report_x')
    expect(router.currentRoute.value.name).toBe('StepReport')
    expect(wrapper.get('[data-testid="report-redirect-not-found"]').text()).toContain('Bericht nicht gefunden')
  })

  it('Ladefehler und Vertragsverletzung: Fehlerzustand mit erneutem Versuch', async () => {
    api.getReport.mockResolvedValue({ success: true, data: { report_id: 'x' } })
    const { wrapper } = await mountAt('/v4/report/report_x')
    expect(wrapper.get('[data-testid="report-redirect-error"]').text()).toContain('Vertragsbruch')
    api.getReport.mockResolvedValue({ success: true, data: reportData({ simulation_id: 'sim_7' }) })
    await wrapper.get('[data-testid="report-redirect-retry"]').trigger('click')
    await flushPromises()
    expect(api.getReport).toHaveBeenCalledTimes(2)
  })

  it('zeigt zunächst den Ladezustand', async () => {
    api.getReport.mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountAt('/v4/report/report_x')
    expect(wrapper.find('[data-testid="report-redirect-loading"]').exists()).toBe(true)
  })
})
