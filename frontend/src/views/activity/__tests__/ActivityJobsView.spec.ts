/**
 * Aktivität → Jobs (#1797, Etappe 2 Ticket 5): Zustände getrennt, Filter,
 * „Zum Lauf" nur mit Simulation, „Abbrechen" nur für laufende Jobs mit Rückfrage.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import de from '../../../i18n/locales/de.json'

const listRuns = vi.fn()
const cancelRun = vi.fn()
vi.mock('../../../api/runs', () => ({
  listRuns: (...a: unknown[]) => listRuns(...a),
  cancelRun: (...a: unknown[]) => cancelRun(...a),
}))
vi.mock('../../../realtime/listInvalidation', () => ({ onListInvalidated: () => () => undefined }))
vi.mock('../../../composables/useShellBreadcrumbs', () => ({ useShellBreadcrumbs: () => undefined }))

import ActivityJobsView from '../ActivityJobsView.vue'

// Kaltes Kompilieren von Ansicht, Tabelle und Router dauert unter Last länger als 5 s.
vi.setConfig({ testTimeout: 30000 })

function job(over: Record<string, unknown>) {
  return {
    run_id: 'run_x',
    run_type: 'simulation_run',
    entity_id: 'e',
    status: 'processing',
    progress: 40,
    message: 'Runde 11 von 24',
    started_at: '2026-10-05T14:10:00Z',
    updated_at: '2026-10-05T14:30:00Z',
    metadata: {},
    linked_ids: {},
    artifacts: {},
    resume_capability: {},
    ...over,
  }
}

const RUNS = [
  job({ run_id: 'run_sim', linked_ids: { simulation_id: 'sim_1' }, updated_at: '2026-10-05T15:00:00Z' }),
  job({ run_id: 'run_graph', run_type: 'graph_build', status: 'completed', progress: 100, completed_at: '2026-10-05T14:11:00Z', updated_at: '2026-10-05T14:59:00Z' }),
  job({ run_id: 'run_stop', status: 'stopped', termination_reason: 'user_stop', updated_at: '2026-10-05T14:58:00Z' }),
  job({ run_id: 'run_budget', status: 'stopped', metadata: { termination_reason: 'budget_cost' }, updated_at: '2026-10-05T14:57:00Z' }),
  job({ run_id: 'run_fail', status: 'failed', termination_reason: 'process_restart', updated_at: '2026-10-05T14:56:00Z' }),
]

function mountView() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: de as never } })
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/activity/jobs', name: 'ActivityJobs', component: stub },
      { path: '/activity/jobs/:runId', name: 'ActivityJobDetail', component: stub },
      { path: '/activity/log', name: 'ActivityLog', component: stub },
      { path: '/simulations/:simulationId', name: 'RunOverview', component: stub },
    ],
  })
  return { router, wrapper: mount(ActivityJobsView, { global: { plugins: [i18n, router] }, attachTo: document.body }) }
}

const rowIds = (w: ReturnType<typeof mountView>['wrapper']) => w.findAll('tr.job-row').map((r) => r.attributes('data-run-id'))

describe('ActivityJobsView', () => {
  beforeEach(() => {
    listRuns.mockReset()
    cancelRun.mockReset()
    listRuns.mockResolvedValue({ success: true, data: { runs: RUNS, total: RUNS.length, aggregation: null } })
    cancelRun.mockResolvedValue({ success: true, status: 'cancel_requested', run_id: 'run_sim' })
  })

  it('zeigt Ladezustand, dann die Jobs neueste zuerst mit getrennten Zuständen', async () => {
    const { wrapper } = mountView()
    expect(wrapper.find('[data-test="loading"]').exists()).toBe(true)
    await flushPromises()
    expect(rowIds(wrapper)).toEqual(['run_sim', 'run_graph', 'run_stop', 'run_budget', 'run_fail'])
    const states = wrapper.findAll('[data-test="state"]').map((b) => b.text())
    expect(states[0]).toContain('Läuft')
    expect(states[1]).toContain('Fertig')
    expect(states[2]).toContain('Gestoppt')
    expect(states[3]).toContain('Budget erschöpft')
    expect(states[4]).toContain('Fehlgeschlagen')
    expect(wrapper.text()).toContain('Prozess wurde neu gestartet')
  })

  it('Tabelle trägt th mit scope, der Job ist per Link erreichbar', async () => {
    const { wrapper } = mountView()
    await flushPromises()
    const heads = wrapper.findAll('thead th')
    expect(heads.length).toBe(7)
    expect(heads.every((h) => h.attributes('scope') === 'col')).toBe(true)
    const link = wrapper.get('tr[data-run-id="run_graph"] a.job-link')
    expect(link.attributes('href')).toBe('/activity/jobs/run_graph')
  })

  it('Klick auf die Zeile öffnet den Job', async () => {
    const { wrapper, router } = mountView()
    await flushPromises()
    await wrapper.get('tr[data-run-id="run_graph"] .num-soft').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ActivityJobDetail')
    expect(router.currentRoute.value.params.runId).toBe('run_graph')
  })

  it('„Zum Lauf" nur bei Jobs mit Simulation', async () => {
    const { wrapper } = mountView()
    await flushPromises()
    const withSim = wrapper.get('tr[data-run-id="run_sim"] [data-test="to-run"]')
    expect(withSim.attributes('href')).toBe('/simulations/sim_1')
    expect(wrapper.find('tr[data-run-id="run_graph"] [data-test="to-run"]').exists()).toBe(false)
  })

  it('„Abbrechen" nur für laufende Jobs, mit Rückfrage', async () => {
    const { wrapper } = mountView()
    await flushPromises()
    expect(wrapper.findAll('[data-test="cancel"]')).toHaveLength(1)
    expect(wrapper.find('tr[data-run-id="run_stop"] [data-test="cancel"]').exists()).toBe(false)
    expect(wrapper.find('tr[data-run-id="run_fail"] [data-test="cancel"]').exists()).toBe(false)

    await wrapper.get('[data-test="cancel"]').trigger('click')
    expect(cancelRun).not.toHaveBeenCalled()
    await wrapper.get('[data-test="cancel-no"]').trigger('click')
    expect(wrapper.find('[data-test="cancel"]').exists()).toBe(true)

    await wrapper.get('[data-test="cancel"]').trigger('click')
    await wrapper.get('[data-test="cancel-yes"]').trigger('click')
    await flushPromises()
    expect(cancelRun).toHaveBeenCalledWith('run_sim')
    expect(wrapper.text()).toContain('Abbruch angefordert')
  })

  it('filtert nach Art und Zustand und zeigt den Leerzustand des Filters', async () => {
    const { wrapper } = mountView()
    await flushPromises()
    await wrapper.get('[data-test="filter-kind"]').setValue('graph_build')
    expect(rowIds(wrapper)).toEqual(['run_graph'])
    await wrapper.get('[data-test="filter-kind"]').setValue('')
    await wrapper.get('[data-test="filter-state"]').setValue('budget')
    expect(rowIds(wrapper)).toEqual(['run_budget'])
    await wrapper.get('[data-test="filter-state"]').setValue('paused')
    expect(wrapper.get('[data-test="empty"]').text()).toContain('Kein Job passt')
  })

  it('zeigt den Leerzustand ohne Jobs', async () => {
    listRuns.mockResolvedValue({ success: true, data: { runs: [], total: 0, aggregation: null } })
    const { wrapper } = mountView()
    await flushPromises()
    expect(wrapper.get('[data-test="empty"]').text()).toContain('Noch keine Jobs')
  })

  it('zeigt einen Ladefehler sichtbar und keinen Leerzustand', async () => {
    listRuns.mockRejectedValue(new Error('Netz weg'))
    const { wrapper } = mountView()
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toContain('Netz weg')
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(false)
  })
})
