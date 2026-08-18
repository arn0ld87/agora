import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const pipeline = vi.hoisted(() => ({
  initialize: vi.fn(),
  refreshGraph: vi.fn(),
  // Issue #1029: pro Test setzbar, damit die Verdrahtung des
  // Degradierungs-Hinweises prüfbar bleibt und nicht nur der Leerfall.
  graphIncomplete: false,
  degradations: { schema_version: 1, events: [] } as {
    schema_version: number
    events: Array<Record<string, unknown>>
  },
}))
const routerPush = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useGraphBuildPipeline', async () => {
  const { ref } = await import('vue')
  return {
    useGraphBuildPipeline: () => ({
      projectData: ref({ project_id: 'project_42' }),
      currentProjectId: ref('project_42'),
      currentPhase: ref(1),
      ontologyProgress: ref({ message: 'ontology' }),
      buildProgress: ref({ progress: 50, message: 'building' }),
      graphData: ref({ graph_id: 'graph_42', nodes: [], edges: [] }),
      systemLogs: ref([{ time: '10:00:00.000', msg: 'building' }]),
      error: ref('Graph build failed'),
      currentRunId: ref(null),
      degradations: ref(pipeline.degradations),
      graphIncomplete: ref(pipeline.graphIncomplete),
      initialize: pipeline.initialize,
      refreshGraph: pipeline.refreshGraph,
    }),
  }
})
const route = vi.hoisted(() => ({
  name: 'StepGraphBuild',
  params: {} as Record<string, unknown>,
  query: {} as Record<string, unknown>,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: vi.fn(), push: routerPush }),
  useRoute: () => route,
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import StepGraphBuildView from '../StepGraphBuildView.vue'

describe('StepGraphBuildView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pipeline.degradations = { schema_version: 1, events: [] }
    pipeline.graphIncomplete = false
    route.query = {}
  })

  it('bindet den Graph-Build-Pipelinezustand an Step1GraphBuild und macht Fehler zugänglich', () => {
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: true,
          Step1GraphBuild: {
            name: 'Step1GraphBuild',
            props: ['projectData', 'currentPhase', 'ontologyProgress', 'buildProgress', 'graphData', 'systemLogs'],
            template: '<section />',
          },
        },
      },
    })

    const step = wrapper.getComponent({ name: 'Step1GraphBuild' })
    expect(step.props()).toMatchObject({
      projectData: { project_id: 'project_42' },
      currentPhase: 1,
      ontologyProgress: { message: 'ontology' },
      buildProgress: { progress: 50, message: 'building' },
      graphData: { graph_id: 'graph_42', nodes: [], edges: [] },
      systemLogs: [{ time: '10:00:00.000', msg: 'building' }],
    })
    expect(wrapper.get('[role="alert"]').text()).toContain('Graph build failed')
  })

  it('initialisiert den neuen Projektpfad nur einmal, auch nachdem die konkrete ID die Route ersetzt', async () => {
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'new' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: true,
          Step1GraphBuild: true,
        },
      },
    })
    await flushPromises()
    await wrapper.setProps({ projectId: 'project_42' })

    expect(pipeline.initialize).toHaveBeenCalledTimes(1)
  })

  it('initialisiert eine echte A→B-Routennavigation mit der neuen Projekt-ID', async () => {
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'project_a' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: true,
          Step1GraphBuild: true,
        },
      },
    })
    await flushPromises()
    await wrapper.setProps({ projectId: 'project_b' })

    expect(pipeline.initialize).toHaveBeenCalledTimes(2)
    expect(pipeline.initialize).toHaveBeenLastCalledWith('project_b')
  })

  it('leitet ein next-step vom Child auf StepEnvSetup weiter', async () => {
    routerPush.mockClear()
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: true,
          Step1GraphBuild: {
            name: 'Step1GraphBuild',
            props: ['projectData', 'currentPhase', 'ontologyProgress', 'buildProgress', 'graphData', 'systemLogs'],
            emits: ['next-step'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper.getComponent({ name: 'Step1GraphBuild' }).vm.$emit('next-step')

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepEnvSetup',
      params: { projectId: 'project_42' },
      query: {},
    })
  })

  // Issue #1234: Schritt 1 verbraucht die Run-Parameter des Dashboard-Starts
  // nicht, ist aber die einzige Station zwischen ihnen und Schritt 3. Ohne
  // Weitergabe endete die Kette hier — der pendingUpload-Store, der sie
  // frueher trug, wird genau in diesem Schritt geleert.
  it('reicht die Run-Parameter aus der Query an Schritt 2 weiter', async () => {
    routerPush.mockClear()
    route.query = { maxRounds: '25', budget: '{"schema_version":1,"max_tokens":5000}' }
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: true,
          Step1GraphBuild: {
            name: 'Step1GraphBuild',
            props: ['projectData', 'currentPhase', 'ontologyProgress', 'buildProgress', 'graphData', 'systemLogs'],
            emits: ['next-step'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper.getComponent({ name: 'Step1GraphBuild' }).vm.$emit('next-step')

    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepEnvSetup',
      params: { projectId: 'project_42' },
      query: { maxRounds: '25', budget: '{"schema_version":1,"max_tokens":5000}' },
    })
  })

  // Issue #1023 (Befund B-08): GraphPanel emittiert refresh/toggle-maximize
  // seit jeher, StepGraphBuildView hatte dafuer nie einen Listener gebunden.
  it('verdrahtet GraphPanel @refresh auf refreshGraph() und @toggle-maximize auf den lokalen Maximize-Zustand', async () => {
    pipeline.refreshGraph.mockClear()
    const graphPanelStub = {
      name: 'GraphPanel',
      props: ['graphData', 'loading', 'currentPhase', 'isMaximized'],
      emits: ['refresh', 'toggle-maximize'],
      template: '<div data-testid="graph-panel-stub" :data-maximized="isMaximized" />',
    }
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: graphPanelStub,
          Step1GraphBuild: true,
        },
      },
    })

    const panel = wrapper.getComponent({ name: 'GraphPanel' })
    expect(panel.props('isMaximized')).toBe(false)

    await panel.vm.$emit('refresh')
    expect(pipeline.refreshGraph).toHaveBeenCalledTimes(1)

    await panel.vm.$emit('toggle-maximize')
    expect(wrapper.getComponent({ name: 'GraphPanel' }).props('isMaximized')).toBe(true)
  })

  // Issue #1029 — der Hinweis muss den Weg vom Composable in die Ansicht
  // finden. Ohne diesen Test wäre die Degradierung zwar erfasst, aber die
  // Oberfläche bliebe genauso stumm wie vorher.
  describe('Degradierungs-Hinweis', () => {
    function mountView() {
      return mount(StepGraphBuildView, {
        props: { projectId: 'project_42' },
        global: {
          mocks: { $t: (key: any) => key },
          stubs: {
            AppShell: { template: '<main><slot /></main>' },
            PageHeader: { template: '<header><slot /></header>' },
            PipelineStepper: true,
            StepModelOverrideChip: true,
            GraphPanel: true,
            Step1GraphBuild: true,
          },
        },
      })
    }

    it('zeigt keinen Hinweis, wenn nichts ausgefallen ist', () => {
      expect(mountView().find('.degradation-notice').exists()).toBe(false)
    })

    it('reicht einen erfassten Ausfall an DegradationNotice durch', () => {
      pipeline.degradations = {
        schema_version: 1,
        events: [
          {
            kind: 'embedding_unavailable',
            severity: 'warning',
            detail: 'Batch-Embedding fehlgeschlagen.',
            occurred_at: '2026-08-02T20:00:00Z',
            occurrences: 1,
            context: {},
          },
        ],
      }

      const notice = mountView().find('.degradation-notice')
      expect(notice.exists()).toBe(true)
      expect(notice.text()).toContain('Batch-Embedding fehlgeschlagen.')
    })

    // Issue #1029, Befund B-24: Ein Graph ohne Beziehungen darf den
    // Folgeschritt nicht freigeben.
    it('meldet einen blockierenden Befund als qualityBlocked an Step1GraphBuild', () => {
      pipeline.degradations = {
        schema_version: 1,
        events: [
          {
            kind: 'graph_below_threshold',
            severity: 'blocking',
            detail: 'Der Graph enthält 3 Entitäten, aber nur 0 Beziehungen.',
            occurred_at: '2026-08-02T20:00:00Z',
            occurrences: 1,
            context: { node_count: 3, edge_count: 0 },
          },
        ],
      }

      const step = mountView().getComponent({ name: 'Step1GraphBuild' })
      expect(step.props('qualityBlocked')).toBe(true)
    })

    it('blockiert den Folgeschritt bei abgebrochenem Build (graph_incomplete)', () => {
      // PR #1371: Ein per Nutzerabbruch behaltener Teilgraph erzeugt keine
      // Degradation — die Liste ist leer, blockiert wird trotzdem.
      pipeline.graphIncomplete = true

      const step = mountView().getComponent({ name: 'Step1GraphBuild' })
      expect(step.props('qualityBlocked')).toBe(true)
    })

    it('lässt eine bloße Warnung den Folgeschritt offen', () => {
      pipeline.degradations = {
        schema_version: 1,
        events: [
          {
            kind: 'embedding_unavailable',
            severity: 'warning',
            detail: 'Batch-Embedding fehlgeschlagen.',
            occurred_at: '2026-08-02T20:00:00Z',
            occurrences: 1,
            context: {},
          },
        ],
      }

      const step = mountView().getComponent({ name: 'Step1GraphBuild' })
      expect(step.props('qualityBlocked')).toBe(false)
    })

    it('gibt den Folgeschritt bei sauberem Build frei', () => {
      const step = mountView().getComponent({ name: 'Step1GraphBuild' })
      expect(step.props('qualityBlocked')).toBe(false)
    })
  })
})
