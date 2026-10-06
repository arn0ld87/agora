import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunGraphView from '@/views/run/RunGraphView.vue'
import GraphLibraryDetailView from '@/views/graph/GraphLibraryDetailView.vue'
import LibraryGraphsView from '@/views/library/LibraryGraphsView.vue'
import {
  CanvasStub,
  graphFixture,
  makeI18n,
  makeRouter,
  projectFixture,
} from '@/components/graph-library/__tests__/fixtures'

const api = vi.hoisted(() => ({
  getProject: vi.fn(),
  getGraphData: vi.fn(),
  getTaskStatus: vi.fn(),
  listProjects: vi.fn(),
  exportGraphMl: vi.fn(),
  getSimulation: vi.fn(),
  listSimulations: vi.fn(),
}))

vi.mock('@/api/graph', () => ({
  getProject: api.getProject,
  getGraphData: api.getGraphData,
  getTaskStatus: api.getTaskStatus,
  listProjects: api.listProjects,
  exportGraphMl: api.exportGraphMl,
}))
vi.mock('@/api/simulation', () => ({
  getSimulation: api.getSimulation,
  listSimulations: api.listSimulations,
}))

const sim = (id: string, projectId = 'proj_1') => ({
  simulation_id: id,
  project_id: projectId,
  status: 'completed',
  created_at: '2026-10-03T10:00:00',
})

async function mountAt(component: object, path: string): Promise<VueWrapper> {
  const router = makeRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [makeI18n(), router, createPinia()], stubs: { GraphCanvas: CanvasStub } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getGraphData.mockResolvedValue({ success: true, data: graphFixture() })
  api.getProject.mockResolvedValue({ success: true, data: projectFixture() })
  api.getSimulation.mockResolvedValue({ success: true, data: sim('sim_1') })
  api.listSimulations.mockResolvedValue({ success: true, data: [sim('sim_1'), sim('sim_2')] })
})

describe('RunGraphView', () => {
  it('löst Lauf → Projekt → Graph auf und zeigt den Leser samt Sprung in die Bibliothek', async () => {
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_1/graph')
    expect(api.getSimulation).toHaveBeenCalledWith('sim_1')
    expect(api.getProject).toHaveBeenCalledWith('proj_1')
    expect(api.getGraphData).toHaveBeenCalledWith('graph_1')
    expect(wrapper.find('[data-testid="gr-counts"]').exists()).toBe(true)
    const link = wrapper.get('[data-testid="open-in-library"]')
    expect(link.attributes('href')).toBe('/graphs/proj_1')
  })

  it('zeigt „kein Graph“ mit Sprung in die Build-Ansicht, wenn das Projekt keinen Graphen hat', async () => {
    api.getProject.mockResolvedValue({
      success: true,
      data: projectFixture({ status: 'created', graph_id: null }),
    })
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_1/graph')
    expect(api.getGraphData).not.toHaveBeenCalled()
    const box = wrapper.get('[data-testid="gpr-no-graph"]')
    expect(box.text()).toContain('Es liegt kein Graph vor')
    expect(box.get('a').attributes('href')).toBe('/v4/graph-build/proj_1')
    expect(wrapper.find('[data-testid="gr-counts"]').exists()).toBe(false)
  })

  it('zeigt Fehler beim Auflösen des Laufs als Alarm', async () => {
    api.getSimulation.mockResolvedValue({ success: false, error: 'Lauf nicht gefunden' })
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_x/graph')
    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('Lauf nicht gefunden')
    expect(api.getProject).not.toHaveBeenCalled()
  })

  it('meldet vertragswidrige Graphdaten statt sie zu rendern', async () => {
    api.getGraphData.mockResolvedValue({ success: true, data: { graph_id: 'graph_1', nodes: 'kaputt', edges: [] } })
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_1/graph')
    expect(wrapper.get('[role="alert"]').text()).toContain('nicht das erwartete Format')
  })

  it('zeigt während des Builds den Fortschritt und den Sprung in die Build-Ansicht', async () => {
    api.getProject.mockResolvedValue({
      success: true,
      data: projectFixture({ status: 'graph_building', graph_id: null, graph_build_task_id: 'task_1' }),
    })
    api.getTaskStatus.mockResolvedValue({
      success: true,
      data: {
        task_id: 'task_1',
        task_type: 'graph_build',
        status: 'processing',
        created_at: 'x',
        updated_at: 'x',
        progress: 40,
        message: 'Chunks werden verarbeitet',
        progress_detail: {},
        metadata: {},
      },
    })
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_1/graph')
    const box = wrapper.get('[data-testid="gpr-building"]')
    expect(box.get('progress').attributes('value')).toBe('40')
    expect(box.text()).toContain('Chunks werden verarbeitet')
    expect(box.get('a').attributes('href')).toBe('/v4/graph-build/proj_1')
    wrapper.unmount()
  })

  it('markiert einen abgebrochenen Build als Teilgraph', async () => {
    api.getProject.mockResolvedValue({
      success: true,
      data: projectFixture({ status: 'graph_incomplete' }),
    })
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_1/graph')
    expect(wrapper.text()).toContain('Teilgraph')
  })
})

describe('GraphLibraryDetailView', () => {
  it('führt „Neuer Lauf auf diesem Graphen“ auf die Build-Ansicht des Projekts', async () => {
    const wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    const link = wrapper.get('[data-testid="new-run"]')
    expect(link.attributes('href')).toBe('/v4/graph-build/proj_1')
    expect(link.text()).toBe('Neuer Lauf auf diesem Graphen')
  })

  it('sperrt „Neuer Lauf“, solange der Graph nicht vollständig gebaut ist', async () => {
    api.getProject.mockResolvedValue({
      success: true,
      data: projectFixture({ status: 'graph_incomplete' }),
    })
    const wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    expect(wrapper.find('[data-testid="new-run"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="new-run-disabled"]').attributes('disabled')).toBeDefined()
  })

  it('listet die Läufe auf diesem Graphen mit Sprung auf die Übersicht', async () => {
    const wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    expect(api.listSimulations).toHaveBeenCalledWith('proj_1')
    const links = wrapper.findAll('.gld__run')
    expect(links.map((l) => l.attributes('href')).sort()).toEqual(['/simulations/sim_1', '/simulations/sim_2'])
    expect(links[0].text()).toContain('Fertig')
  })

  it('sagt ausdrücklich, wenn kein Lauf den Graphen nutzt, und meldet Ladefehler', async () => {
    api.listSimulations.mockResolvedValue({ success: true, data: [] })
    let wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)

    api.listSimulations.mockRejectedValue(new Error('Netz weg'))
    wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    expect(wrapper.get('[data-testid="runs-error"]').text()).toContain('Netz weg')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(false)
  })
})

describe('LibraryGraphsView', () => {
  it('zeigt Kacheln mit Name, Quelle, Zahl der Läufe und Sprung auf /graphs/:projectId', async () => {
    api.listProjects.mockResolvedValue({
      success: true,
      data: [projectFixture(), projectFixture({ project_id: 'proj_2', name: 'Zweiter', files: [], updated_at: '2026-09-01T10:00:00' })],
    })
    api.listSimulations.mockResolvedValue({ success: true, data: [sim('sim_1'), sim('sim_2'), sim('sim_3', 'proj_2')] })
    const wrapper = await mountAt(LibraryGraphsView, '/library/graphs')
    const tiles = wrapper.findAll('.lgv__tile')
    expect(tiles).toHaveLength(2)
    expect(tiles[0].attributes('href')).toBe('/graphs/proj_1')
    expect(tiles[0].text()).toContain('Geburtshilfe Hollerau')
    expect(tiles[0].text()).toContain('seed.md')
    expect(tiles[0].text()).toContain('2 Läufe')
    expect(tiles[1].text()).toContain('1 Lauf')
    expect(wrapper.get('[data-testid="graph-count"]').text()).toBe('2')
  })

  it('zeigt den Leerzustand', async () => {
    api.listProjects.mockResolvedValue({ success: true, data: [] })
    const wrapper = await mountAt(LibraryGraphsView, '/library/graphs')
    expect(wrapper.find('[data-testid="library-empty"]').exists()).toBe(true)
    expect(wrapper.find('.lgv__tile').exists()).toBe(false)
  })

  it('zeigt einen Fehler der Projektliste als Alarm mit Wiederholen', async () => {
    api.listProjects.mockRejectedValue(new Error('Server down'))
    const wrapper = await mountAt(LibraryGraphsView, '/library/graphs')
    expect(wrapper.get('[data-testid="library-error"]').text()).toContain('Server down')
    expect(wrapper.find('[data-testid="library-empty"]').exists()).toBe(false)
  })

  it('gibt ausgefallene Lauf-Zahlen nicht als 0 aus', async () => {
    api.listProjects.mockResolvedValue({ success: true, data: [projectFixture()] })
    api.listSimulations.mockRejectedValue(new Error('x'))
    const wrapper = await mountAt(LibraryGraphsView, '/library/graphs')
    expect(wrapper.get('.lgv__tile').text()).toContain('Läufe unbekannt')
    expect(wrapper.text()).toContain('Die Zahl der Läufe konnte nicht geladen werden.')
  })
})
