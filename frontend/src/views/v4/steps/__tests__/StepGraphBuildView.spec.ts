import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const pipeline = vi.hoisted(() => ({ initialize: vi.fn() }))
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
      initialize: pipeline.initialize,
    }),
  }
})
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: vi.fn(), push: routerPush }),
  useRoute: () => ({ name: 'StepGraphBuild', params: {} }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import StepGraphBuildView from '../StepGraphBuildView.vue'

describe('StepGraphBuildView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
    })
  })
})
