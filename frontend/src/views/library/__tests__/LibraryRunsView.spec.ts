/**
 * Bibliothek → Laeufe (#1797): Kacheln/Liste, Filter ?view=, Fassungsliste,
 * Mehrfachauswahl, Leerzustand.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

const listRuns = vi.fn()
const listReports = vi.fn()
const listProjects = vi.fn()
const listPersonaTemplates = vi.fn()
vi.mock('@/api/runs', () => ({ listRuns: (...a: unknown[]) => listRuns(...a) }))
vi.mock('@/api/report', () => ({ listReports: (...a: unknown[]) => listReports(...a) }))
vi.mock('@/api/graph', () => ({ listProjects: (...a: unknown[]) => listProjects(...a) }))
vi.mock('@/api/simulation', () => ({ listPersonaTemplates: (...a: unknown[]) => listPersonaTemplates(...a) }))

import LibraryRunsView from '../LibraryRunsView.vue'

// Das Einhaengen der ganzen Ansicht samt Router und i18n braucht auf langsamen Rechnern mehrere Sekunden.
vi.setConfig({ testTimeout: 20_000 })

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
const stub = { template: '<div/>' }

function run(id: string, sim: string, status: string, opts: { reason?: string; updated?: string; runType?: string } = {}) {
  return {
    run_id: id,
    run_type: opts.runType ?? 'simulation_run',
    entity_id: sim,
    status,
    progress: status === 'processing' ? 46 : 100,
    message: '',
    started_at: '2026-10-06T08:00:00Z',
    updated_at: opts.updated ?? '2026-10-06T10:00:00Z',
    linked_ids: { simulation_id: sim },
    termination_reason: opts.reason ?? null,
    summary: { document_name: `Quelle ${sim}` },
  }
}

function report(id: string, sim: string, status: string, created: string, requirement = `Frage zu ${sim}`) {
  return {
    schema_version: 2, report_id: id, simulation_id: sim, graph_id: 'g1', simulation_requirement: requirement, status,
    created_at: created, completed_at: created,
  }
}

const RUNS = [
  run('run_a', 'sim_a', 'processing', { updated: '2026-10-06T12:00:00Z' }),
  run('run_b', 'sim_b', 'completed', { updated: '2026-10-06T11:00:00Z' }),
  run('run_c', 'sim_c', 'failed', { updated: '2026-10-06T10:00:00Z' }),
  run('run_d', 'sim_d', 'completed', { updated: '2026-10-06T09:00:00Z' }),
]
const REPORTS = [
  report('report_b1', 'sim_b', 'completed', '2026-10-05T10:00:00Z'),
  report('report_b2', 'sim_b', 'incomplete', '2026-10-06T10:00:00Z'),
]

function setup(runs: unknown[], reports: unknown[]) {
  listRuns.mockReset().mockResolvedValue({ success: true, data: { runs, total: runs.length, aggregation: null } })
  listReports.mockReset().mockImplementation(async (params?: { simulation_id?: string }) => ({
    success: true,
    data: params?.simulation_id ? reports.filter((r) => (r as { simulation_id: string }).simulation_id === params.simulation_id) : reports,
  }))
  listProjects.mockReset().mockResolvedValue({ success: true, data: [] })
  listPersonaTemplates.mockReset().mockResolvedValue({ success: true, data: { templates: [] } })
}

async function mountAt(url: string): Promise<{ wrapper: VueWrapper; router: ReturnType<typeof makeTestRouter> }> {
  const router = makeTestRouter([
    { path: '/library/runs', name: 'LibraryRuns', component: stub },
    { path: '/library/runs/new', name: 'NewRun', component: stub },
    { path: '/simulations/:simulationId', name: 'RunOverview', component: stub },
    { path: '/compare/:simulationId?', name: 'Compare', component: stub },
    { path: '/v4/report/:reportId', name: 'StepReport', component: stub },
  ])
  await router.push(url)
  await router.isReady()
  const wrapper = mount(LibraryRunsView, { global: { plugins: [router, i18n, createPinia()] }, attachTo: document.body })
  await flushPromises()
  return { wrapper, router }
}

const ids = (w: VueWrapper) => w.findAll('[data-run-id]').map((el) => el.attributes('data-run-id'))

describe('LibraryRunsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    setup(RUNS, REPORTS)
  })

  it('zeigt Laeufe als Kacheln mit Frage als Titel und Zustand als Wort', async () => {
    const { wrapper } = await mountAt('/library/runs')
    expect(ids(wrapper)).toEqual(['sim_a', 'sim_b', 'sim_c', 'sim_d'])
    const b = wrapper.find('[data-run-id="sim_b"]')
    expect(b.find('h3').text()).toBe('Frage zu sim_b')
    expect(b.text()).toContain('Quelle sim_b')
    // unvollstaendig (juengster Bericht) ist nicht „Fertig“
    expect(b.find('.state-mark').text()).toContain('Unvollständig')
    expect(b.find('.state-mark').text()).not.toContain('Fertig')
    expect(wrapper.find('[data-run-id="sim_d"] .state-mark').text()).toContain('Fertig')
    expect(wrapper.find('[data-run-id="sim_c"] .state-mark').text()).toContain('Fehlgeschlagen')
    expect(wrapper.find('[data-run-id="sim_a"]').text()).toContain('Fortschritt 46 %')
  })

  it('Kachel-Klick fuehrt auf RunOverview mit simulationId', async () => {
    const { wrapper, router } = await mountAt('/library/runs')
    await wrapper.find('[data-run-id="sim_d"] a.run-tile__link').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('RunOverview')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_d')
  })

  it('merkt die Wahl Kacheln/Liste', async () => {
    const { wrapper } = await mountAt('/library/runs')
    expect(wrapper.find('[data-testid="runs-list"]').classes()).toContain('runs-grid--tiles')
    await wrapper.find('[data-layout="list"]').trigger('click')
    expect(wrapper.find('[data-testid="runs-list"]').classes()).toContain('runs-grid--list')
    wrapper.unmount()
    const again = await mountAt('/library/runs')
    expect(again.wrapper.find('[data-testid="runs-list"]').classes()).toContain('runs-grid--list')
  })

  it('Band „Im Blick“ ist nur sichtbar, wenn etwas laeuft oder dich braucht', async () => {
    const { wrapper } = await mountAt('/library/runs')
    expect(wrapper.find('[data-testid="runs-band"]').exists()).toBe(true)
    wrapper.unmount()
    setup([run('run_d', 'sim_d', 'completed')], [])
    const calm = await mountAt('/library/runs')
    expect(calm.wrapper.find('[data-testid="runs-band"]').exists()).toBe(false)
  })

  it('?view=running filtert auf laufende Laeufe', async () => {
    const { wrapper } = await mountAt('/library/runs?view=running')
    expect(ids(wrapper)).toEqual(['sim_a'])
  })

  it('?view=attention filtert auf Laeufe, die dich brauchen (fehlgeschlagen, unvollstaendig)', async () => {
    const { wrapper } = await mountAt('/library/runs?view=attention')
    expect(ids(wrapper)).toEqual(['sim_b', 'sim_c'])
  })

  it('?view=with-report zeigt nur Laeufe mit Bericht samt Zahl der Fassungen', async () => {
    const { wrapper } = await mountAt('/library/runs?view=with-report')
    expect(ids(wrapper)).toEqual(['sim_b'])
    expect(wrapper.find('[data-run-id="sim_b"] .run-tile__reports').text()).toContain('2 Fassungen')
  })

  it('der Filterknopf schreibt ?view= in die Adresse', async () => {
    const { wrapper, router } = await mountAt('/library/runs')
    await wrapper.find('[data-view="with-report"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBe('with-report')
    expect(ids(wrapper)).toEqual(['sim_b'])
    await wrapper.find('[data-view="all"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBeUndefined()
  })

  it('Fassungsliste klappt auf (Datum, Zustand) und jede Zeile fuehrt auf die alte Berichtsansicht', async () => {
    const { wrapper, router } = await mountAt('/library/runs?view=with-report')
    expect(wrapper.find('[data-testid="run-versions"]').exists()).toBe(false)
    const toggle = wrapper.find('[data-run-id="sim_b"] button[aria-expanded]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    await flushPromises()
    expect(listReports).toHaveBeenCalledWith({ simulation_id: 'sim_b' })
    expect(toggle.attributes('aria-expanded')).toBe('true')
    const rows = wrapper.findAll('[data-testid="run-versions"] li')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Fassung 2')
    expect(rows[0].text()).toContain('Unvollständig')
    expect(rows[1].text()).toContain('Fassung 1')
    expect(rows[1].text()).toContain('Fertig')
    await rows[1].find('a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('StepReport')
    expect(router.currentRoute.value.params.reportId).toBe('report_b1')
  })

  it('zweiter Knopf fuehrt zur juengsten Fassung', async () => {
    const { wrapper, router } = await mountAt('/library/runs?view=with-report')
    const latest = wrapper.findAll('[data-run-id="sim_b"] .run-tile__reports a')[0]
    await latest.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.reportId).toBe('report_b2')
  })

  it('meldet einen Ladefehler der Fassungsliste sichtbar', async () => {
    const { wrapper } = await mountAt('/library/runs?view=with-report')
    listReports.mockRejectedValue(new Error('boom'))
    await wrapper.find('[data-run-id="sim_b"] button[aria-expanded]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="run-versions"]').attributes('role')).toBe('region')
    expect(wrapper.find('[data-testid="run-versions"] [role="alert"]').exists()).toBe(true)
  })

  it('Vergleichen gibt es erst bei genau zwei markierten Laeufen', async () => {
    const { wrapper, router } = await mountAt('/library/runs')
    expect(wrapper.find('[data-testid="runs-selection"]').exists()).toBe(false)
    const box = (id: string) => wrapper.find(`[data-run-id="${id}"] input[type="checkbox"]`)
    await box('sim_a').setValue(true)
    expect(wrapper.find('[data-testid="runs-compare"]').attributes('disabled')).toBeDefined()
    await box('sim_c').setValue(true)
    const compare = wrapper.find('[data-testid="runs-compare"]')
    expect(compare.attributes('disabled')).toBeUndefined()
    await box('sim_d').setValue(true)
    expect(wrapper.find('[data-testid="runs-compare"]').attributes('disabled')).toBeDefined()
    await box('sim_d').setValue(false)
    await wrapper.find('[data-testid="runs-compare"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Compare')
    expect(router.currentRoute.value.params.simulationId).toBe('sim_a')
  })

  it('Leerzustand: ein Satz und „Neuer Lauf“ (Route NewRun)', async () => {
    setup([], [])
    const { wrapper, router } = await mountAt('/library/runs')
    expect(ids(wrapper)).toEqual([])
    const empty = wrapper.find('[data-testid="runs-empty"]')
    expect(empty.text()).toContain('Ein Lauf ist ein ganzes Vorhaben')
    await wrapper.find('[data-testid="runs-empty-new"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('NewRun')
  })

  it('zeigt vor dem ersten Laden keinen Leerzustand', async () => {
    listRuns.mockReset().mockReturnValue(new Promise(() => {}))
    listReports.mockReset().mockReturnValue(new Promise(() => {}))
    listProjects.mockReset().mockReturnValue(new Promise(() => {}))
    listPersonaTemplates.mockReset().mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountAt('/library/runs')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(false)
  })
})
