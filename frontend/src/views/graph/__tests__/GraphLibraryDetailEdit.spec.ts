/**
 * Verdrahtung der bearbeitbaren Ansicht (#1808, Etappe 8).
 *
 * Der Lauf bleibt lesend (Entscheid 9), die Bibliothek bekommt die
 * Bearbeitungsspalte. Beides wird hier an der echten Ansicht geprueft, damit
 * die Unterscheidung nicht nur in den Komponententests steht.
 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RunGraphView from '@/views/run/RunGraphView.vue'
import GraphLibraryDetailView from '@/views/graph/GraphLibraryDetailView.vue'
import {
  CanvasStub,
  graphFixture,
  makeI18n,
  makeRouter,
  projectFixture,
} from '@/components/graph-library/__tests__/fixtures'
import { GraphEditTestId } from '@/contracts/testIds'

const api = vi.hoisted(() => ({
  getProject: vi.fn(),
  getGraphData: vi.fn(),
  getTaskStatus: vi.fn(),
  listSimulations: vi.fn(),
  exportGraphMl: vi.fn(),
  getSimulation: vi.fn(),
  getGraphLock: vi.fn(),
  createEntity: vi.fn(),
  duplicateGraph: vi.fn(),
}))

vi.mock('@/api/graph', () => ({
  getProject: api.getProject,
  getGraphData: api.getGraphData,
  getTaskStatus: api.getTaskStatus,
  exportGraphMl: api.exportGraphMl,
}))
vi.mock('@/api/simulation', () => ({
  getSimulation: api.getSimulation,
  listSimulations: api.listSimulations,
}))
vi.mock('@/api/graphEdit', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/graphEdit')>()
  return {
    ...actual,
    getGraphLock: api.getGraphLock,
    createEntity: api.createEntity,
    duplicateGraph: api.duplicateGraph,
  }
})

const sim = { simulation_id: 'sim_1', project_id: 'proj_1', status: 'completed', created_at: '2026-10-03' }

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
  api.getSimulation.mockResolvedValue({ success: true, data: sim })
  api.listSimulations.mockResolvedValue({ success: true, data: [sim] })
  api.getGraphLock.mockResolvedValue({ graph_id: 'graph_1', locked: false, used_by: [] })
  api.createEntity.mockResolvedValue({})
})

describe('Graph-Detail mit Bearbeitung', () => {
  it('zeigt in der Bibliothek Sperrzustand und Schreibwege', async () => {
    const wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.root}"]`).exists()).toBe(true)
    expect(wrapper.get(`[data-testid="${GraphEditTestId.lockBadge}"]`).text()).toBe('Bearbeitbar')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.createEntity}"]`).exists()).toBe(true)
  })

  it('lässt im Lauf keine Schreibwege zu', async () => {
    const wrapper = await mountAt(RunGraphView, '/simulations/sim_1/graph')
    expect(wrapper.find(`[data-testid="${GraphEditTestId.root}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${GraphEditTestId.createEntity}"]`).exists()).toBe(false)
    expect(wrapper.find('[data-testid="gr-counts"]').exists()).toBe(true)
  })

  it('schlägt den Namen der Kopie mit dem Anzeigamen des Projekts vor', async () => {
    api.getGraphLock.mockResolvedValue({
      graph_id: 'graph_1',
      locked: true,
      used_by: [{ simulation_id: 'sim_1', status: 'completed', project_id: 'proj_1', branch_name: null }],
    })
    api.duplicateGraph.mockResolvedValue({
      run_id: 'run_dup_1',
      source_graph_id: 'graph_1',
      graph_id: 'graph_2',
      project_id: 'proj_kopie',
      status: 'pending',
      progress: 0,
      message: 'Kopie angelegt',
      error: null,
    })
    const wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')

    const field = wrapper.get(`[data-testid="${GraphEditTestId.duplicateName}"]`)
    expect((field.element as HTMLInputElement).value).toBe(projectFixture().name)
    await wrapper.get(`[data-testid="${GraphEditTestId.duplicateStart}"]`).trigger('click')
    await flushPromises()

    expect(api.duplicateGraph).toHaveBeenCalledWith('graph_1', { name: projectFixture().name })
    expect(wrapper.get(`[data-testid="${GraphEditTestId.duplicateState}"]`).attributes('data-status')).toBe(
      'pending',
    )
    wrapper.unmount()
  })

  it('lädt die Graphdaten nach einer gelungenen Änderung neu', async () => {
    api.createEntity.mockResolvedValue({ uuid: '33333333-3333-4333-8333-333333333333' })
    const wrapper = await mountAt(GraphLibraryDetailView, '/graphs/proj_1')
    const before = api.getGraphData.mock.calls.length

    await wrapper.get(`[data-testid="${GraphEditTestId.createEntity}"]`).trigger('click')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityName}"]`).setValue('Neuer Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityType}"]`).setValue('Ort')
    await wrapper.get(`[data-testid="${GraphEditTestId.entityForm}"]`).trigger('submit')
    await flushPromises()

    expect(api.createEntity).toHaveBeenCalled()
    expect(api.getGraphData.mock.calls.length).toBeGreaterThan(before)
  })
})