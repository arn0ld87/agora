import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => ({
    name: 'StepSimulation',
    params: { simulationId: 'sim_x' },
    query: { projectId: 'project_42' },
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: 'de' } }),
  createI18n: () => ({ install: vi.fn() }),
}))

import StepSimulationView from '../StepSimulationView.vue'

describe('StepSimulationView — Navigation', () => {
  beforeEach(() => {
    routerPush.mockClear()
  })

  it('leitet go-back mit projectId aus route.query an StepEnvSetup weiter', async () => {
    const wrapper = mount(StepSimulationView, {
      props: { simulationId: 'sim_x' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Tabs: {
            name: 'Tabs',
            props: ['modelValue', 'tabs', 'urlSync'],
            emits: ['update:modelValue'],
            template: '<section />',
          },
          Step3Simulation: {
            name: 'Step3Simulation',
            props: ['simulationId'],
            emits: ['go-back'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step3Simulation' })
      .vm.$emit('go-back')

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepEnvSetup',
      params: { projectId: 'project_42' },
    })
  })
})
