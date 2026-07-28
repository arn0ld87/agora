import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => ({ name: 'StepEnvSetup', params: {} }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: 'de' } }),
  createI18n: () => ({ install: vi.fn() }),
}))

import StepEnvSetupView from '../StepEnvSetupView.vue'

describe('StepEnvSetupView — Navigation', () => {
  beforeEach(() => {
    routerPush.mockClear()
  })

  it('leitet next-step mit simulationId an StepSimulation weiter', async () => {
    const wrapper = mount(StepEnvSetupView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Step2EnvSetup: {
            name: 'Step2EnvSetup',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back', 'add-log', 'update-status'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x' })

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulation',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })

  it('ignoriert next-step ohne nichtleere simulationId', async () => {
    const wrapper = mount(StepEnvSetupView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Step2EnvSetup: {
            name: 'Step2EnvSetup',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back', 'add-log', 'update-status'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: '' })

    expect(routerPush).not.toHaveBeenCalled()
  })

  it('leitet go-back an StepGraphBuild weiter', async () => {
    const wrapper = mount(StepEnvSetupView, {
      props: { projectId: 'project_42' },
      global: {
        mocks: { $t: (key: any) => key },
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Step2EnvSetup: {
            name: 'Step2EnvSetup',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back', 'add-log', 'update-status'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('go-back')

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepGraphBuild',
      params: { projectId: 'project_42' },
    })
  })
})
