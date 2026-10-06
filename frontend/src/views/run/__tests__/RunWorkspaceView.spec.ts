/**
 * Lauf-Arbeitsbereich und Übersicht (Etappe 2, #1797): Reiterziele,
 * Deaktivierung mit Grund, Zustände je Stufe, genau ein nächster Schritt,
 * Lade-/Fehler-/Nicht-gefunden-Zustand.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import de from '@/i18n/locales/de.json'
import { ApiError } from '@/api/envelope'

const api = vi.hoisted(() => ({
  getSimulation: vi.fn(),
  getProject: vi.fn(),
  listRuns: vi.fn(),
  getRun: vi.fn(),
  listReports: vi.fn(),
  getReportEvidence: vi.fn(),
  getRunLlmRouting: vi.fn(),
  getRoutingDefaults: vi.fn(),
  generateReport: vi.fn(),
}))
vi.mock('@/api/simulation', () => ({ getSimulation: api.getSimulation }))
vi.mock('@/api/graph', () => ({ getProject: api.getProject }))
vi.mock('@/api/runs', () => ({ listRuns: api.listRuns, getRun: api.getRun }))
vi.mock('@/api/report', () => ({
  listReports: api.listReports,
  getReportEvidence: api.getReportEvidence,
  generateReport: api.generateReport,
}))
vi.mock('@/api/llmRouting', async (orig) => ({
  ...(await orig<typeof import('@/api/llmRouting')>()),
  getRunLlmRouting: api.getRunLlmRouting,
}))
vi.mock('@/api/llmRoutingDefaults', async (orig) => ({
  ...(await orig<typeof import('@/api/llmRoutingDefaults')>()),
  getRoutingDefaults: api.getRoutingDefaults,
}))

import { PENDING_RUN_PARAMS_PREFIX, writePendingRunParams } from '@/composables/new-run/pendingRunParams'
import RunWorkspaceView from '../RunWorkspaceView.vue'
import RunOverviewView from '../RunOverviewView.vue'

const Stub = defineComponent({ render: () => h('div') })
const PickerStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  setup(_p, { emit }) {
    return () =>
      h('button', {
        type: 'button',
        'data-testid': 'picker-stub',
        onClick: () => emit('update:modelValue', { provider_connection_id: 'conn-x', model_id: 'neu-modell', source: 'explicit' }),
      }, 'pick')
  },
})
const MonitorStub = defineComponent({ props: ['runId', 'status', 'terminationReason'], render: () => h('div', { 'data-testid': 'monitor-stub' }) })

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId',
        name: 'RunWorkspace',
        component: RunWorkspaceView,
        props: true,
        children: [
          { path: '', name: 'RunOverview', component: RunOverviewView },
          { path: 'graph', name: 'RunGraph', component: Stub },
        ],
      },
      { path: '/v4/env-setup/:projectId', name: 'StepEnvSetup', component: Stub },
      { path: '/v4/graph-build/:projectId', name: 'StepGraphBuild', component: Stub },
      { path: '/v4/simulation/:simulationId', name: 'StepSimulation', component: Stub },
      { path: '/v4/simulation/:simulationId/feed', name: 'StepSimulationFeed', component: Stub },
      { path: '/v4/report/:reportId', name: 'StepReport', component: Stub },
      { path: '/v4/simulation/:simulationId/interviews', name: 'RunInterviewsLegacy', component: Stub },
      { path: '/library/runs', name: 'LibraryRuns', component: Stub },
    ],
  })
}

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } as never })

const PROJECT = {
  project_id: 'proj_1', name: 'Quelle A', status: 'graph_completed', created_at: 'x', updated_at: 'x',
  files: [], total_text_length: 1, ontology: null, analysis_summary: null, graph_id: 'g1',
  graph_build_task_id: null, simulation_requirement: 'Wie reagiert die Branche auf die Abgabe?',
  chunk_size: 1, chunk_overlap: 0, llm_model: null, llm_provider: null, llm_profile_id: null,
  ai_model_ref: null, error: null,
}

function runDetail(runType: string, over: Record<string, unknown> = {}) {
  return {
    run_id: `run_${runType}`, run_type: runType, entity_id: 'e', status: 'completed', progress: 100,
    started_at: '2026-10-05T10:00:00Z', updated_at: '2026-10-05T10:04:12Z', completed_at: '2026-10-05T10:04:12Z',
    summary: { model: 'gpt-5.1', persona_count: 12 }, ...over,
  }
}

function report(over: Record<string, unknown> = {}) {
  return {
    schema_version: 2, report_id: 'report_1', simulation_id: 'sim_1', graph_id: 'g1',
    simulation_requirement: 'Frage aus Bericht', status: 'completed', created_at: '2026-10-05T11:00:00Z', ...over,
  }
}

interface Setup { projectId?: string | null; jobs?: ReturnType<typeof runDetail>[]; reports?: ReturnType<typeof report>[] }

function arrange({ projectId = 'proj_1', jobs = [], reports = [] }: Setup = {}) {
  api.getSimulation.mockResolvedValue({ success: true, data: { simulation_id: 'sim_1', project_id: projectId, status: 'ready' } })
  api.getProject.mockResolvedValue({ success: true, data: PROJECT })
  api.listRuns.mockResolvedValue({ success: true, data: { runs: jobs, total: jobs.length } })
  api.getRun.mockImplementation(async (id: string) => {
    const j = jobs.find((x) => x.run_id === id)
    return { success: true, data: { ...j, usage: { totals: { total_tokens: 2000, cost_micros: 410000, duration_ms: 5000 } } } }
  })
  api.listReports.mockResolvedValue({ success: true, data: reports })
  api.getReportEvidence.mockResolvedValue({ success: true, data: {} })
  const stageOf: Record<string, string> = {
    graph_build: 'graph_build', simulation_prepare: 'persona_generation',
    simulation_run: 'simulation_rounds', report_generate: 'report_generation',
  }
  api.getRunLlmRouting.mockImplementation(async (id: string) => {
    const j = jobs.find((x) => x.run_id === id)
    const stage = stageOf[j?.run_type ?? ''] ?? 'x'
    return { snapshots: { [stage]: { stage, provider_id: 'prov-1', model: `snap-${j?.run_type}`, routing_version: 1 } } }
  })
  api.getRoutingDefaults.mockResolvedValue({
    global_default: { provider_id: 'prov-d', model: 'std-global', reasoning_effort: 'none', provider_options: {} },
    stage_overrides: {}, routing_version: 1, updated_at: 'x',
  })
}

async function mountAt(path = '/simulations/sim_1') {
  const router = makeRouter()
  await router.push(path)
  const wrapper = mount(
    defineComponent({ render: () => h(RouterView) }),
    { global: { plugins: [createPinia(), i18n, router], stubs: { RunResourceMonitor: MonitorStub, AiModelPicker: PickerStub } } },
  )
  await flushPromises()
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => vi.clearAllMocks())

describe('RunWorkspaceView: Reiter', () => {
  it('zeigt Frage als Titel, sechs Reiter mit Zielen und aria-current an der Übersicht', async () => {
    arrange({ jobs: [runDetail('simulation_run')], reports: [report()] })
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="run-title"]').text()).toBe('Wie reagiert die Branche auf die Abgabe?')
    const tabs = wrapper.findAll('[data-testid^="run-tab-"]')
    expect(tabs).toHaveLength(6)
    const href = (k: string) => wrapper.get(`[data-testid="run-tab-${k}"]`).attributes('href')
    expect(href('overview')).toBe('/simulations/sim_1')
    expect(href('graph')).toBe('/simulations/sim_1/graph')
    expect(href('personas')).toBe('/v4/env-setup/proj_1')
    expect(href('simulation')).toBe('/v4/simulation/sim_1/feed')
    expect(href('report')).toBe('/v4/report/report_1')
    expect(href('interviews')).toBe('/v4/simulation/sim_1/interviews')
    const current = wrapper.findAll('[aria-current="page"]').filter((e) => e.attributes('data-testid')?.startsWith('run-tab-'))
    expect(current).toHaveLength(1)
    expect(current[0]!.attributes('data-testid')).toBe('run-tab-overview')
  })

  it('wählt den jüngsten Bericht für den Berichts-Reiter', async () => {
    arrange({
      reports: [
        report({ report_id: 'report_old', created_at: '2026-10-01T00:00:00Z' }),
        report({ report_id: 'report_new', created_at: '2026-10-05T00:00:00Z' }),
      ],
    })
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="run-tab-report"]').attributes('href')).toBe('/v4/report/report_new')
  })

  it('Bericht und Personas deaktiviert mit Grund, Interviews bleibt aktiv', async () => {
    arrange({ projectId: null })
    const { wrapper } = await mountAt()
    for (const k of ['personas', 'report']) {
      const el = wrapper.get(`[data-testid="run-tab-${k}"]`)
      expect(el.element.tagName).toBe('BUTTON')
      expect(el.attributes('aria-disabled')).toBe('true')
      expect(el.attributes('href')).toBeUndefined()
    }
    expect(wrapper.get('[data-testid="run-tab-personas"]').text()).toContain('lässt sich nicht auflösen')
    expect(wrapper.get('[data-testid="run-tab-report"]').text()).toContain('noch keinen Bericht')
    expect(wrapper.get('[data-testid="run-tab-interviews"]').attributes('href')).toBe('/v4/simulation/sim_1/interviews')
  })
})

describe('RunOverviewView: Stufen', () => {
  it('zeigt fünf Zeilen und je Zeile genau einen nächsten Schritt', async () => {
    arrange({ jobs: [runDetail('graph_build'), runDetail('simulation_prepare'), runDetail('simulation_run')], reports: [report()] })
    const { wrapper } = await mountAt()
    for (const k of ['graph', 'personas', 'simulation', 'report', 'interviews']) {
      const row = wrapper.get(`[data-testid="stage-row-${k}"]`)
      expect(row.findAll('[data-testid^="stage-next-"]')).toHaveLength(1)
    }
    expect(wrapper.get('[data-testid="stage-next-graph"]').attributes('href')).toBe('/simulations/sim_1/graph')
    expect(wrapper.get('[data-testid="stage-next-report"]').attributes('href')).toBe('/v4/report/report_1')
    expect(wrapper.get('[data-testid="stage-model-graph"]').text()).toContain('snap-graph_build')
  })

  describe('Startparameter aus dem Startdialog (#1799)', () => {
    beforeEach(() => window.sessionStorage.clear())

    it('mit vorgemerktem Eintrag trägt der Startlink Runden und Tage', async () => {
      writePendingRunParams('sim_1', { maxRounds: 10, simulationDays: 2, budget: null })
      arrange({ jobs: [runDetail('graph_build'), runDetail('simulation_prepare')] })
      const { wrapper } = await mountAt()
      const href = wrapper.get('[data-testid="stage-next-simulation"]').attributes('href') ?? ''
      expect(href.startsWith('/v4/simulation/sim_1?')).toBe(true)
      expect(href).toContain('maxRounds=10')
      expect(href).toContain('simulationDays=2')
    })

    it('ohne Eintrag bleibt der Startlink ohne Query', async () => {
      arrange({ jobs: [runDetail('graph_build'), runDetail('simulation_prepare')] })
      const { wrapper } = await mountAt()
      expect(wrapper.get('[data-testid="stage-next-simulation"]').attributes('href')).toBe('/v4/simulation/sim_1')
    })

    it('ein beschädigter Eintrag wird ignoriert', async () => {
      window.sessionStorage.setItem(`${PENDING_RUN_PARAMS_PREFIX}sim_1`, '{"maxRounds":"viele"')
      arrange({ jobs: [runDetail('graph_build'), runDetail('simulation_prepare')] })
      const { wrapper } = await mountAt()
      expect(wrapper.get('[data-testid="stage-next-simulation"]').attributes('href')).toBe('/v4/simulation/sim_1')
    })
  })

  it('Verbrauch kommt aus dem Ledger, Fehlendes steht als "nicht erfasst"', async () => {
    arrange({ jobs: [runDetail('simulation_run')] })
    const { wrapper } = await mountAt()
    const sim = wrapper.get('[data-testid="stage-row-simulation"]').text()
    expect(sim).toContain('4 min 12 s')
    expect(sim).toContain('2k')
    const interviews = wrapper.get('[data-testid="stage-row-interviews"]').text()
    expect(interviews).toContain('nicht erfasst')
    expect(wrapper.get('[data-testid="stage-model-interviews"]').text()).toBe('nicht erfasst')
  })

  it('Unvollständig trägt Text und Symbol, die sich von Fertig unterscheiden, und nennt den Grund', async () => {
    arrange({
      jobs: [runDetail('simulation_run'), runDetail('report_generate')],
      reports: [report({ status: 'incomplete', missing_sections: ['Fazit', 'Risiken'] })],
    })
    const { wrapper } = await mountAt()
    const mark = (k: string) => wrapper.get(`[data-testid="stage-row-${k}"] [data-testid="run-state-mark"]`)
    expect(mark('report').attributes('data-state')).toBe('incomplete')
    expect(mark('report').text()).toContain('Unvollständig')
    expect(mark('report').text()).toContain('◐')
    expect(mark('simulation').attributes('data-state')).toBe('done')
    expect(mark('simulation').text()).toContain('✓')
    expect(wrapper.get('[data-testid="stage-notes-report"]').text()).toContain('2 Abschnitte fehlen')
  })

  it('process_restart erscheint als fehlgeschlagen mit Grund', async () => {
    arrange({ jobs: [runDetail('simulation_run', { status: 'failed', metadata: { termination_reason: 'process_restart' } })] })
    const { wrapper } = await mountAt()
    const row = wrapper.get('[data-testid="stage-row-simulation"]')
    expect(row.get('[data-testid="run-state-mark"]').attributes('data-state')).toBe('failed')
    expect(row.get('[data-testid="stage-notes-simulation"]').text()).toContain('neu gestartet')
    expect(wrapper.get('[data-testid="stage-next-simulation"]').attributes('data-step')).toBe('resume')
  })

  it('evidence_omitted wird benannt', async () => {
    arrange({ reports: [report()] })
    api.getReportEvidence.mockResolvedValue({ success: true, evidence_omitted: { reason: 'contract_violation' } })
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="stage-notes-report"]').text()).toContain('evidence_omitted')
    expect(wrapper.get('[data-testid="stage-row-report"] [data-testid="run-state-mark"]').attributes('data-state')).toBe('degraded')
  })

  it('Graph-Karte führt auf RunGraph; Budget nutzt den Simulations-Job', async () => {
    arrange({ jobs: [runDetail('graph_build'), runDetail('simulation_run')] })
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="card-graph-link"]').attributes('href')).toBe('/simulations/sim_1/graph')
    expect(wrapper.get('[data-testid="card-personas"]').text()).toContain('nicht erfasst')
    expect(wrapper.findComponent(MonitorStub).props('runId')).toBe('run_simulation_run')
  })
})

describe('RunWorkspaceView: Laden und Fehler', () => {
  it('zeigt zuerst den Ladezustand', async () => {
    arrange()
    api.getSimulation.mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="run-loading"]').text()).toContain('wird geladen')
  })

  it('unbekannter Lauf: "Lauf nicht gefunden"', async () => {
    arrange()
    api.getSimulation.mockRejectedValue(new ApiError({ code: 'not_found', status: 404, message: 'nope' }))
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="run-not-found"]').text()).toContain('Lauf nicht gefunden')
    expect(wrapper.find('[data-testid="run-tabs"]').exists()).toBe(false)
  })

  it('Ladefehler wird sichtbar gemeldet und lässt sich wiederholen', async () => {
    arrange()
    api.listRuns.mockRejectedValueOnce(new Error('Netz weg'))
    const { wrapper } = await mountAt()
    const err = wrapper.get('[data-testid="run-error"]')
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('Netz weg')
    await wrapper.get('[data-testid="run-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="run-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="run-overview"]').exists()).toBe(true)
  })

  it('Vertragsbruch der Berichtsliste ist ein sichtbarer Fehler, kein stilles Weglassen', async () => {
    arrange()
    api.listReports.mockResolvedValue({ success: true, data: [{ report_id: 'x' }] })
    const { wrapper } = await mountAt()
    expect(wrapper.get('[data-testid="run-error"]').text()).toContain('Vertragsbruch')
  })
})

describe('RunOverviewView: Modell je Stufe (#1799)', () => {
  const model = (w: { get: (s: string) => { text: () => string } }, k: string) => w.get(`[data-testid="stage-model-${k}"]`).text()

  it('Snapshot gewinnt vor summary.model; Berichtszeile zeigt das Berichtsmodell', async () => {
    arrange({
      jobs: [runDetail('simulation_run'), runDetail('report_generate')],
      reports: [report()],
    })
    const { wrapper } = await mountAt()
    expect(model(wrapper, 'simulation')).toContain('snap-simulation_run')
    expect(model(wrapper, 'simulation')).toContain('prov-1')
    expect(model(wrapper, 'report')).toContain('snap-report_generate')
    expect(model(wrapper, 'report')).not.toContain('gpt-5.1')
  })

  it('fällt ohne Snapshot auf usage.by_model zurück und zeigt alle Modelle', async () => {
    arrange({ jobs: [runDetail('simulation_run')] })
    api.getRunLlmRouting.mockResolvedValue({ snapshots: {} })
    api.getRun.mockResolvedValue({
      success: true,
      data: { ...runDetail('simulation_run'), usage: { totals: { total_tokens: 1, cost_micros: 1, duration_ms: 1 }, by_model: { 'm-a': {}, 'm-b': {} } } },
    })
    const { wrapper } = await mountAt()
    const text = model(wrapper, 'simulation')
    expect(text).toContain('m-a')
    expect(text).toContain('m-b')
    expect(text).not.toContain('gpt-5.1')
  })

  it('Ladefehler des Snapshots fällt sichtbar auf den Rückfall und wird geloggt', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    arrange({ jobs: [runDetail('simulation_run')] })
    api.getRunLlmRouting.mockRejectedValue(new Error('boom'))
    const { wrapper } = await mountAt()
    expect(model(wrapper, 'simulation')).toContain('nicht erfasst')
    expect(wrapper.get('[data-testid="stage-model-error-simulation"]').text()).toContain('konnte nicht geladen werden')
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  it('Interviews bleiben "nicht erfasst"', async () => {
    arrange({ jobs: [runDetail('simulation_run')] })
    const { wrapper } = await mountAt()
    expect(model(wrapper, 'interviews')).toBe('nicht erfasst')
  })

  it('Stufe ohne Job zeigt "Standard: <Modell>" mit Hilfetext und nennt es am Startknopf', async () => {
    arrange({ jobs: [] })
    const { wrapper } = await mountAt()
    const cell = wrapper.get('[data-testid="stage-model-personas"]')
    expect(cell.text()).toContain('Standard: std-global')
    expect(cell.find('[data-testid="stage-model-default-personas"]').attributes('title')).toContain('gilt, wenn beim Start nichts anderes gewählt wird')
    const start = wrapper.get('[data-testid="stage-next-personas"]')
    expect(start.text()).toContain('mit std-global')
    expect(start.attributes('aria-label')).toContain('mit std-global')
  })
})

describe('RunOverviewView: Bericht neu erzeugen', () => {
  it('erscheint nur in der Berichtszeile und sendet ai_model_ref + force_regenerate', async () => {
    arrange({ jobs: [runDetail('simulation_run')], reports: [report()] })
    api.generateReport.mockResolvedValue({ success: true, data: {} })
    const { wrapper } = await mountAt()
    expect(wrapper.findAll('[data-testid^="stage-regenerate-"]').map((e) => e.attributes('data-testid'))).toEqual(['stage-regenerate-report'])
    await wrapper.get('[data-testid="stage-regenerate-report"]').trigger('click')
    await flushPromises()
    const body = document.body
    expect(body.textContent).toContain('Legt eine weitere Fassung an. Bestehende Fassungen bleiben erhalten.')
    ;(body.querySelector('[data-testid="picker-stub"]') as HTMLElement).click()
    await flushPromises()
    ;(body.querySelector('[data-testid="regenerate-confirm"]') as HTMLElement).click()
    await flushPromises()
    expect(api.generateReport).toHaveBeenCalledWith({
      simulation_id: 'sim_1',
      force_regenerate: true,
      ai_model_ref: { provider_connection_id: 'conn-x', model_id: 'neu-modell', source: 'explicit' },
    })
    wrapper.unmount()
  })

  it('zeigt Fehler sichtbar und lässt den Dialog offen', async () => {
    arrange({ jobs: [runDetail('simulation_run')], reports: [report()] })
    api.generateReport.mockResolvedValue({ success: false, error: 'Rate-Limit erreicht' })
    const { wrapper } = await mountAt()
    await wrapper.get('[data-testid="stage-regenerate-report"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-testid="picker-stub"]') as HTMLElement).click()
    await flushPromises()
    ;(document.body.querySelector('[data-testid="regenerate-confirm"]') as HTMLElement).click()
    await flushPromises()
    expect(document.body.querySelector('[data-testid="regenerate-error"]')?.textContent).toContain('Rate-Limit erreicht')
    wrapper.unmount()
  })

  it('fehlt ohne Bericht und bei laufendem Berichtsjob', async () => {
    arrange({ jobs: [runDetail('simulation_run')] })
    let { wrapper } = await mountAt()
    expect(wrapper.find('[data-testid="stage-regenerate-report"]').exists()).toBe(false)
    wrapper.unmount()
    arrange({ jobs: [runDetail('simulation_run'), runDetail('report_generate', { status: 'processing', completed_at: null })], reports: [report()] })
    ;({ wrapper } = await mountAt())
    expect(wrapper.find('[data-testid="stage-regenerate-report"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
