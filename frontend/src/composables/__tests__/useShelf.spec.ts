/**
 * useShelf — Unit-Tests (Block B3, Fundament).
 *
 * 20 Tests:
 *  endeavorKey (3):
 *   1. simulation_id gewinnt vor project_id
 *   2. project_id greift ohne simulation_id
 *   3. run_id als letzter Rueckgriff
 *  nextActionFor (8, Tabellen-Test via it.each ueber run_type x status)
 *  buildShelfObjects (7):
 *   1. zwei Jobs derselben simulation_id -> eine Lauf-Zeile, Status des juengsten Jobs
 *   2. status processing -> active gesetzt, pausable nur bei simulation_run
 *   3. status paused -> active.status paused
 *   4. beanspruchtes Projekt kein Graph-Objekt; unbeanspruchtes schon
 *   5. Bericht eigenes Objekt mit nextAction StepReport, auch bei Lauf zur selben Simulation
 *   6. Personasatz ohne jede ID wird uebersprungen
 *   7. Sortierung: neuestes updatedAt zuerst
 *  useShelf.reload (2):
 *   1. Promise.allSettled: eine Quelle rejected, andere drei liefern trotzdem; error = shelf.partialLoad
 *   2. counts je kind, filtered filtert, activeObjects nur mit active
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { RunDetail } from '../../contracts/runsContract'
import type { Report } from '../../contracts/reportContract'
import type { ProjectResponse } from '../../api/graph'
import type { PersonaTemplateRecord } from '../../api/simulation'

// --- API-Mocks (vi.hoisted, damit die vi.mock-Factories sie referenzieren koennen) ---
const runsApi = vi.hoisted(() => ({ listRuns: vi.fn() }))
const reportApi = vi.hoisted(() => ({ listReports: vi.fn() }))
const graphApi = vi.hoisted(() => ({ listProjects: vi.fn() }))
const simulationApi = vi.hoisted(() => ({ listPersonaTemplates: vi.fn() }))

vi.mock('../../api/runs', () => runsApi)
vi.mock('../../api/report', () => reportApi)
vi.mock('../../api/graph', () => graphApi)
vi.mock('../../api/simulation', () => simulationApi)

import { endeavorKey, nextActionFor, buildShelfObjects, useShelf } from '../useShelf'

// --- t-Stub: gibt Schluessel (+ JSON der Values) zurueck, Assertions laufen ueber Schluessel ---
const t = (key: string, values?: Record<string, unknown>): string =>
  values ? `${key}:${JSON.stringify(values)}` : key

// --- Fixtures -------------------------------------------------------------

/** RunDetail-Factory — typkonform zum Contract (src/contracts/runsContract.ts). */
function makeRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    run_id: 'run_1',
    run_type: 'simulation_run',
    entity_id: 'entity_1',
    parent_run_id: null,
    status: 'completed',
    progress: 100,
    message: '',
    error: null,
    started_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:05:00Z',
    branch_label: null,
    metadata: {},
    linked_ids: {},
    artifacts: {},
    resume_capability: {},
    summary: null,
    eta_seconds: null,
    log_tail: null,
    metrics: null,
    ...overrides,
  }
}

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    schema_version: 2,
    report_id: 'rep_1',
    simulation_id: 'sim_1',
    graph_id: 'graph_1',
    simulation_requirement: 'Testfrage',
    status: 'completed',
    outline: null,
    markdown_content: '',
    missing_sections: [],
    created_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-02T00:00:00Z',
    error: null,
    has_evidence: false,
    evidence_sections: 0,
    red_team_findings: [],
    simulation_snapshot: null,
    run_degradations: [],
    ...overrides,
  }
}

function makeProject(overrides: Partial<ProjectResponse> = {}): ProjectResponse {
  return {
    project_id: 'proj_1',
    project_name: 'Projekt',
    status: 'ready',
    ...overrides,
  }
}

function makeTemplate(overrides: Partial<PersonaTemplateRecord> = {}): PersonaTemplateRecord {
  return {
    template_id: 'tpl_1',
    name: 'Vorlage',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

// === endeavorKey ===========================================================

describe('endeavorKey', () => {
  it('simulation_id gewinnt vor project_id', () => {
    const run = makeRun({ linked_ids: { simulation_id: 'sim_1', project_id: 'proj_1' } })
    expect(endeavorKey(run)).toBe('sim_1')
  })

  it('project_id greift, wenn keine simulation_id vorhanden ist', () => {
    const run = makeRun({ linked_ids: { project_id: 'proj_1' } })
    expect(endeavorKey(run)).toBe('proj_1')
  })

  it('run_id ist der letzte Rueckgriff, wenn weder simulation_id noch project_id vorhanden sind', () => {
    const run = makeRun({ run_id: 'run_42', linked_ids: {} })
    expect(endeavorKey(run)).toBe('run_42')
  })
})

// === nextActionFor ==========================================================

describe('nextActionFor — Tabellen-Test ueber run_type x status', () => {
  type Case = {
    name: string
    run: Partial<RunDetail>
    expected: null | { to: string; labelKey: string; kind: string; params?: Record<string, string> }
  }

  const cases: Case[] = [
    {
      name: 'processing + simulation_run + sim_id -> StepSimulationFeed (watch)',
      run: { status: 'processing', run_type: 'simulation_run', linked_ids: { simulation_id: 'sim_1' } },
      expected: { to: 'StepSimulationFeed', labelKey: 'shelf.action.watch', kind: 'neutral', params: { simulationId: 'sim_1' } },
    },
    {
      name: 'paused + sim_id -> StepSimulation (resume, accent)',
      run: { status: 'paused', linked_ids: { simulation_id: 'sim_1' } },
      expected: { to: 'StepSimulation', labelKey: 'shelf.action.resume', kind: 'accent', params: { simulationId: 'sim_1' } },
    },
    {
      name: 'failed -> RunDetail (inspectFailure, warn)',
      run: { status: 'failed', run_id: 'run_failed' },
      expected: { to: 'RunDetail', labelKey: 'shelf.action.inspectFailure', kind: 'warn', params: { id: 'run_failed' } },
    },
    {
      name: 'stopped -> RunDetail (inspectStopped, warn)',
      run: { status: 'stopped', run_id: 'run_stopped' },
      expected: { to: 'RunDetail', labelKey: 'shelf.action.inspectStopped', kind: 'warn', params: { id: 'run_stopped' } },
    },
    {
      name: 'completed + graph_build + project_id -> StepEnvSetup (preparePersonas)',
      run: { status: 'completed', run_type: 'graph_build', linked_ids: { project_id: 'proj_1' } },
      expected: { to: 'StepEnvSetup', labelKey: 'shelf.action.preparePersonas', kind: 'accent', params: { projectId: 'proj_1' } },
    },
    {
      name: 'completed + simulation_run + report_id -> StepReport (readReport)',
      run: { status: 'completed', run_type: 'simulation_run', linked_ids: { report_id: 'rep_1', simulation_id: 'sim_1' } },
      expected: { to: 'StepReport', labelKey: 'shelf.action.readReport', kind: 'accent', params: { reportId: 'rep_1' } },
    },
    {
      name: 'completed + simulation_run ohne report_id, mit sim_id -> StepSimulation (createReport)',
      run: { status: 'completed', run_type: 'simulation_run', linked_ids: { simulation_id: 'sim_1' } },
      expected: { to: 'StepSimulation', labelKey: 'shelf.action.createReport', kind: 'accent', params: { simulationId: 'sim_1' } },
    },
    {
      name: 'completed + unbekannter run_type -> null',
      run: { status: 'completed', run_type: 'mystery_type', linked_ids: {} },
      expected: null,
    },
  ]

  it.each(cases)('$name', ({ run, expected }) => {
    const result = nextActionFor(makeRun(run), t)
    if (expected === null) {
      expect(result).toBeNull()
      return
    }
    expect(result).not.toBeNull()
    expect(result?.to.name).toBe(expected.to)
    expect(result?.label).toBe(t(expected.labelKey))
    expect(result?.kind).toBe(expected.kind)
    if (expected.params) expect(result?.to.params).toEqual(expected.params)
  })
})

// === buildShelfObjects =======================================================

describe('Gruppierung ueber die ganze Pipeline', () => {
  it('fasst graph_build (nur project_id) und simulation_prepare (beide IDs) zu EINEM Lauf zusammen', () => {
    // graph_build kennt nur die project_id, das folgende
    // simulation_prepare kennt beide. Ohne transitive Aufloesung
    // zerfaellt ein Lauf hier in zwei Zeilen.
    const build = makeRun({
      run_id: 'run_build',
      run_type: 'graph_build',
      linked_ids: { project_id: 'proj_1' },
      updated_at: '2026-01-01T00:00:00Z',
    })
    const prepare = makeRun({
      run_id: 'run_prep',
      run_type: 'simulation_prepare',
      linked_ids: { project_id: 'proj_1', simulation_id: 'sim_1' },
      updated_at: '2026-01-02T00:00:00Z',
    })

    const objs = buildShelfObjects([build, prepare], [], [], [], t)
    const laufObjs = objs.filter((o) => o.kind === 'lauf')

    expect(laufObjs.length).toBe(1)
    expect(laufObjs[0].id).toBe('sim_1')
    expect(laufObjs[0].statusLine).toContain('"n":2')
  })

  it('haelt zwei Vorhaben ohne gemeinsame ID getrennt', () => {
    const a = makeRun({ run_id: 'run_a', linked_ids: { project_id: 'proj_a' } })
    const b = makeRun({ run_id: 'run_b', linked_ids: { project_id: 'proj_b' } })

    const laufObjs = buildShelfObjects([a, b], [], [], [], t).filter((o) => o.kind === 'lauf')
    expect(laufObjs.length).toBe(2)
  })

  it('verkettet auch ueber mehrere Glieder (build -> prepare -> run)', () => {
    const build = makeRun({ run_id: 'r1', run_type: 'graph_build', linked_ids: { project_id: 'p' }, updated_at: '2026-01-01T00:00:00Z' })
    const prep = makeRun({ run_id: 'r2', run_type: 'simulation_prepare', linked_ids: { project_id: 'p', simulation_id: 's' }, updated_at: '2026-01-02T00:00:00Z' })
    const run = makeRun({ run_id: 'r3', run_type: 'simulation_run', linked_ids: { simulation_id: 's' }, updated_at: '2026-01-03T00:00:00Z' })

    const laufObjs = buildShelfObjects([build, prep, run], [], [], [], t).filter((o) => o.kind === 'lauf')
    expect(laufObjs.length).toBe(1)
    expect(laufObjs[0].statusLine).toContain('"n":3')
  })
})

describe('buildShelfObjects', () => {
  it('zwei Jobs mit derselben simulation_id ergeben eine Lauf-Zeile mit Status des juengsten Jobs und Job-Zaehler', () => {
    const older = makeRun({
      run_id: 'run_old',
      linked_ids: { simulation_id: 'sim_1' },
      updated_at: '2026-01-01T00:00:00Z',
      message: 'alter Job',
    })
    const newer = makeRun({
      run_id: 'run_new',
      linked_ids: { simulation_id: 'sim_1' },
      updated_at: '2026-01-02T00:00:00Z',
      message: 'neuer Job',
    })

    const objs = buildShelfObjects([older, newer], [], [], [], t)
    const laufObjs = objs.filter((o) => o.kind === 'lauf')

    expect(laufObjs.length).toBe(1)
    expect(laufObjs[0].id).toBe('sim_1')
    expect(laufObjs[0].updatedAt).toBe('2026-01-02T00:00:00Z')
    expect(laufObjs[0].statusLine).toContain('neuer Job')
    expect(laufObjs[0].statusLine).toContain('shelf.status.jobs')
    expect(laufObjs[0].statusLine).toContain('"n":2')
  })

  it('Job mit status processing setzt active; pausable nur bei run_type simulation_run', () => {
    const simRun = makeRun({ status: 'processing', run_type: 'simulation_run', linked_ids: { simulation_id: 'sim_2' } })
    const [simObj] = buildShelfObjects([simRun], [], [], [], t)
    expect(simObj.active).not.toBeNull()
    expect(simObj.active?.status).toBe('processing')
    expect(simObj.active?.pausable).toBe(true)
    expect(simObj.active?.simulationId).toBe('sim_2')

    const graphRun = makeRun({ run_id: 'run_gb', status: 'processing', run_type: 'graph_build', linked_ids: { project_id: 'proj_2' } })
    const [graphObj] = buildShelfObjects([graphRun], [], [], [], t)
    expect(graphObj.active).not.toBeNull()
    expect(graphObj.active?.pausable).toBe(false)
  })

  it('Job mit status paused setzt active.status auf paused', () => {
    const run = makeRun({ status: 'paused', linked_ids: { simulation_id: 'sim_3' } })
    const [obj] = buildShelfObjects([run], [], [], [], t)
    expect(obj.active?.status).toBe('paused')
  })

  it('Projekt, dessen project_id von einem Job beansprucht ist, bekommt kein eigenes Graph-Objekt; unbeanspruchtes Projekt schon', () => {
    const run = makeRun({ linked_ids: { project_id: 'proj_claimed' } })
    const projects = [
      makeProject({ project_id: 'proj_claimed', project_name: 'Beansprucht' }),
      makeProject({ project_id: 'proj_free', project_name: 'Frei' }),
    ]

    const objs = buildShelfObjects([run], [], projects, [], t)
    const graphObjs = objs.filter((o) => o.kind === 'graph')

    expect(graphObjs.map((o) => o.id)).toEqual(['proj_free'])
  })

  it('Bericht bekommt eigenes Objekt mit nextAction StepReport, auch wenn ein Lauf zur selben Simulation existiert', () => {
    const run = makeRun({ linked_ids: { simulation_id: 'sim_4' } })
    const report = makeReport({
      report_id: 'rep_4',
      simulation_id: 'sim_4',
      simulation_requirement: 'Wie hoch ist die Akzeptanz?',
      outline: {
        title: 'Titel',
        summary: 'Zusammenfassung',
        sections: [
          { title: 'Abschnitt 1', description: 'Beschreibung 1' },
          { title: 'Abschnitt 2', description: 'Beschreibung 2' },
        ],
      },
    })

    const objs = buildShelfObjects([run], [report], [], [], t)
    const berichtObjs = objs.filter((o) => o.kind === 'bericht')

    expect(berichtObjs.length).toBe(1)
    expect(berichtObjs[0].id).toBe('rep_4')
    expect(berichtObjs[0].nextAction?.to.name).toBe('StepReport')
    expect(berichtObjs[0].nextAction?.to.params).toEqual({ reportId: 'rep_4' })
  })

  it('Personasatz ohne jede ID wird uebersprungen', () => {
    const templates: PersonaTemplateRecord[] = [
      { template_id: '', username: '', name: '' },
      makeTemplate({ template_id: 'tpl_ok', name: 'Gueltig' }),
    ]

    const objs = buildShelfObjects([], [], [], templates, t)
    const personaObjs = objs.filter((o) => o.kind === 'personasatz')

    expect(personaObjs.length).toBe(1)
    expect(personaObjs[0].id).toBe('tpl_ok')
  })

  it('sortiert Objekte nach updatedAt absteigend (neuestes zuerst)', () => {
    const run = makeRun({ run_id: 'run_sort', updated_at: '2026-01-01T00:00:00Z', linked_ids: {} })
    const report = makeReport({ report_id: 'rep_sort', completed_at: '2026-03-01T00:00:00Z', created_at: '2026-03-01T00:00:00Z' })
    const project = makeProject({ project_id: 'proj_sort' }) as ProjectResponse & { updated_at?: string }
    project.updated_at = '2026-02-01T00:00:00Z'

    const objs = buildShelfObjects([run], [report], [project], [], t)
    expect(objs.map((o) => o.id)).toEqual(['rep_sort', 'proj_sort', 'run_sort'])
  })
})

// === useShelf.reload =========================================================

describe('dynamische Statusschluessel — Locale-Treffer vs. Rohwert', () => {
  // t-Stub, der sich wie vue-i18n verhaelt: bekannte Schluessel werden
  // uebersetzt, unbekannte kommen als Schluessel zurueck.
  const dict: Record<string, string> = {
    'shelf.status.report_generating': 'Bericht wird geschrieben',
    'shelf.status.project_graph_incomplete': 'Graph unvollstaendig (abgebrochen)',
  }
  const tReal = (key: string): string => dict[key] ?? key

  it('uebersetzt einen Berichtsstatus, den die Locales kennen', () => {
    const objs = buildShelfObjects([], [makeReport({ status: 'generating' })], [], [], tReal)
    expect(objs.find((o) => o.kind === 'bericht')?.statusLine).toBe('Bericht wird geschrieben')
  })

  it('uebersetzt einen Projektstatus, den die Locales kennen', () => {
    const objs = buildShelfObjects([], [], [makeProject({ status: 'graph_incomplete' })], [], tReal)
    expect(objs.find((o) => o.kind === 'graph')?.statusLine).toBe('Graph unvollstaendig (abgebrochen)')
  })

  it('zeigt den Rohstatus statt des Schluessels, wenn die Locales ihn nicht kennen', () => {
    // Backend-Enums wachsen schneller als Uebersetzungen. Ein unbekannter
    // Wert darf nie als „shelf.status.report_xyz“ in der Ablage landen.
    const objs = buildShelfObjects(
      [],
      [makeReport({ status: 'kuenftiger_status' as Report['status'] })],
      [makeProject({ status: 'kuenftiger_projektstatus' })],
      [],
      tReal,
    )
    expect(objs.find((o) => o.kind === 'bericht')?.statusLine).toBe('kuenftiger_status')
    expect(objs.find((o) => o.kind === 'graph')?.statusLine).toBe('kuenftiger_projektstatus')
    expect(objs.some((o) => o.statusLine.startsWith('shelf.status.'))).toBe(false)
  })
})

describe('useShelf.reload', () => {
  it('Promise.allSettled: eine Quelle rejected, die anderen drei liefern trotzdem Objekte; error enthaelt shelf.partialLoad', async () => {
    runsApi.listRuns.mockRejectedValue(new Error('Runs-Dienst nicht erreichbar'))
    reportApi.listReports.mockResolvedValue({ success: true, data: [makeReport({ report_id: 'rep_partial' })] })
    graphApi.listProjects.mockResolvedValue({ success: true, data: [makeProject({ project_id: 'proj_partial' })] })
    // persona-library liefert die Envelope, Templates unter data.templates
    simulationApi.listPersonaTemplates.mockResolvedValue({ success: true, data: { count: 1, templates: [makeTemplate({ template_id: 'tpl_partial' })] } })

    const { reload, objects, error } = useShelf(t)
    await reload()

    expect(error.value).toContain('shelf.partialLoad')
    const kinds = objects.value.map((o) => o.kind).sort()
    expect(kinds).toEqual(['bericht', 'graph', 'personasatz'])
  })

  it('counts zaehlt je kind korrekt; filtered filtert; activeObjects enthaelt nur Objekte mit active', async () => {
    const activeRun = makeRun({
      run_id: 'run_active',
      status: 'processing',
      run_type: 'simulation_run',
      linked_ids: { simulation_id: 'sim_active' },
    })
    const doneRun = makeRun({
      run_id: 'run_done',
      status: 'completed',
      run_type: 'simulation_run',
      linked_ids: { simulation_id: 'sim_done', report_id: 'rep_done' },
    })

    runsApi.listRuns.mockResolvedValue({ success: true, data: { runs: [activeRun, doneRun], total: 2, aggregation: null } })
    reportApi.listReports.mockResolvedValue({ success: true, data: [makeReport({ report_id: 'rep_1' })] })
    graphApi.listProjects.mockResolvedValue({ success: true, data: [makeProject({ project_id: 'proj_1' })] })
    simulationApi.listPersonaTemplates.mockResolvedValue({ success: true, data: { count: 1, templates: [makeTemplate({ template_id: 'tpl_1' })] } })

    const { reload, counts, filtered, activeObjects, filter } = useShelf(t)
    await reload()

    expect(counts.value).toEqual({ alle: 5, lauf: 2, bericht: 1, personasatz: 1, graph: 1 })

    filter.value = 'bericht'
    expect(filtered.value.length).toBe(1)
    expect(filtered.value.every((o) => o.kind === 'bericht')).toBe(true)

    expect(activeObjects.value.length).toBe(1)
    expect(activeObjects.value[0].active?.runId).toBe('run_active')
  })
})
