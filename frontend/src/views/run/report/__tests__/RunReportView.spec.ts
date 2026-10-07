import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'
import { evidenceMap, listEnvelope, reportData } from '@/composables/run/report/__tests__/reportFixtures'
import RunReportView from '../RunReportView.vue'

const api = vi.hoisted(() => ({
  listReports: vi.fn(),
  getReport: vi.fn(),
  getReportEvidence: vi.fn(),
  getReportStatus: vi.fn(),
  generateReport: vi.fn(),
  getAgentLog: vi.fn(),
  getConsoleLog: vi.fn(),
}))
vi.mock('@/api/report', () => api)

const Stub = defineComponent({ render: () => h('div') })

async function mountAt(path: string, hasGraph: boolean | null = true) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/simulations/:simulationId/report/:reportId?', name: 'RunReport', component: RunReportView, props: true },
      { path: '/library/runs', name: 'LibraryRuns', component: Stub },
    ],
  })
  await router.push(path)
  await router.isReady()
  const provide = hasGraph === null ? {} : { [RUN_WORKSPACE_KEY as symbol]: { data: ref({ hasGraph }) } }
  const wrapper = mount(
    defineComponent({ render: () => h(RunReportView, { simulationId: 'sim_1', reportId: router.currentRoute.value.params.reportId as string | undefined }) }),
    { global: { plugins: [router, createI18n({ legacy: false, locale: 'de', messages: { de } as never })], provide, stubs: { RunReportRegenerate: true, ReportLiveLogPane: true } } },
  )
  await flushPromises()
  return { router, wrapper }
}

beforeEach(() => {
  vi.clearAllMocks()
  const rep = reportData()
  api.listReports.mockResolvedValue(listEnvelope([rep]))
  api.getReport.mockResolvedValue({ success: true, data: rep })
  api.getReportEvidence.mockResolvedValue({ success: true, data: evidenceMap() })
  api.getReportStatus.mockResolvedValue({ success: false })
})

describe('RunReportView', () => {
  it('Dreispalter: Kopf, Gliederung, Lesetext und Seitenspalte; kein h1', async () => {
    const { wrapper } = await mountAt('/simulations/sim_1/report')
    expect(wrapper.find('[data-testid="report-header"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="report-outline"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="report-reading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="report-side"]').exists()).toBe(true)
    // Kein h1 der Ansicht selbst (ein h1 im Berichtstext aus dem Markdown zählt nicht).
    expect(wrapper.findAll('h1').filter((h) => !h.element.closest('.rr-read__prose'))).toHaveLength(0)
    expect(wrapper.findAll('[data-testid^="report-outline-item-"]')).toHaveLength(2)
  })

  it('Lauf ohne Graph und ohne Fassung: Erklärung statt Startknopf, kein Fehler', async () => {
    api.listReports.mockResolvedValue(listEnvelope([]))
    const { wrapper } = await mountAt('/simulations/sim_1/report', false)
    const note = wrapper.get('[data-testid="report-no-graph"]')
    expect(note.text()).toBe('Dieser Lauf hat keinen Wissensgraphen; Berichte stützen sich auf Belege aus dem Graphen.')
    expect(wrapper.find('[data-testid="report-start-button"]').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('Lauf ohne Graph, aber mit vorhandener Fassung: Bericht bleibt lesbar', async () => {
    const { wrapper } = await mountAt('/simulations/sim_1/report', false)
    expect(wrapper.find('[data-testid="report-no-graph"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="report-reading"]').exists()).toBe(true)
  })

  it('?panel=questions öffnet Nachfragen; Umschalten schreibt ?panel=; ?section= und ?claim= werden gespiegelt', async () => {
    const { wrapper, router } = await mountAt('/simulations/sim_1/report/report_1?panel=questions&claim=c9&section=2')
    expect(wrapper.get('[data-testid="report-side-tab-questions"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid="report-outline-item-2"]').attributes('aria-current')).toBe('location')
    await wrapper.get('[data-testid="report-side-tab-evidence"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({ panel: 'evidence', claim: 'c9', section: '2' })
    await wrapper.get('[data-testid="report-outline-item-1"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.section).toBe('1')
  })

  it('unvollständiger Bericht: Hinweisband direkt unter dem Kopf', async () => {
    const inc = reportData({ status: 'incomplete', missing_sections: ['Akteure'] })
    api.listReports.mockResolvedValue(listEnvelope([inc]))
    api.getReport.mockResolvedValue({ success: true, data: inc })
    const { wrapper } = await mountAt('/simulations/sim_1/report')
    const html = wrapper.html()
    expect(html.indexOf('report-header')).toBeLessThan(html.indexOf('report-banner'))
    expect(html.indexOf('report-banner')).toBeLessThan(html.indexOf('report-grid'))
    expect(wrapper.get('[data-testid="report-banner-missing"]').text()).toContain('Akteure')
  })
})
