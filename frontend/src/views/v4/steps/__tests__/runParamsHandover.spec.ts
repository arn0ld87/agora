import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

// Regressionstest fuer B-09/B-27: Runden/Tage aus Schritt 2 kamen in Schritt 3
// nie an. Beide Views werden hier gemeinsam geprueft, weil der Fehler nicht in
// einer Datei lag, sondern in der Uebergabe zwischen beiden.

const routerPush = vi.fn()
const route: { name: string; query: Record<string, unknown>; params: Record<string, unknown> } = {
  name: 'StepSimulation',
  query: {},
  params: {},
}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => route,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import StepEnvSetupView from '../StepEnvSetupView.vue'
import StepSimulationView from '../StepSimulationView.vue'

const i18nMock = { $t: (key: string) => key }

function mountEnvSetup() {
  return mount(StepEnvSetupView, {
    props: { projectId: 'project_42' },
    shallow: true,
    global: {
      mocks: i18nMock,
      stubs: {
        // Slot-tragende Huellen muessen ihre Slots rendern, sonst sieht der
        // Test die zu pruefenden Kinder nicht.
        AppShell: { template: '<main><slot /></main>' },
        PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
        Step2EnvSetup: {
          name: 'Step2EnvSetup',
          props: ['simulationId'],
          emits: ['next-step', 'go-back', 'add-log', 'update-status'],
          template: '<section />',
        },
      },
    },
  })
}

function mountSimulation() {
  return mount(StepSimulationView, {
    props: { simulationId: 'sim_x' },
    shallow: true,
    global: {
      mocks: i18nMock,
      stubs: {
        // Slot-tragende Huellen muessen ihre Slots rendern, sonst sieht der
        // Test die zu pruefenden Kinder nicht.
        AppShell: { template: '<main><slot /></main>' },
        PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
        Step3Simulation: {
          name: 'Step3Simulation',
          props: ['simulationId', 'maxRounds', 'simulationDays'],
          emits: ['go-back'],
          template: '<section />',
        },
        Tabs: {
          name: 'Tabs',
          props: ['modelValue', 'tabs', 'urlSync'],
          emits: ['update:modelValue'],
          template: '<nav />',
        },
      },
    },
  })
}

beforeEach(() => {
  routerPush.mockClear()
  route.name = 'StepSimulation'
  route.query = {}
})

describe('Schritt 2 -> Schritt 3: Uebergabe der Run-Parameter', () => {
  it('haengt uebersteuerte Runden/Tage an die Query der Folge-Route', async () => {
    const wrapper = mountEnvSetup()

    await wrapper.getComponent({ name: 'Step2EnvSetup' }).vm.$emit('next-step', {
      simulationId: 'sim_x',
      maxRounds: 7,
      simulationDays: 2,
    })

    // Ohne Query gingen die Werte verloren: die Route reicht via ``props: true``
    // ausschliesslich Route-Params durch.
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulation',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42', maxRounds: '7', simulationDays: '2' },
    })
  })

  it('haelt die Query sauber, wenn der Nutzer den Auto-Wert nicht anfasst', async () => {
    const wrapper = mountEnvSetup()

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x' })

    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulation',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })
})

describe('Schritt 3: Uebernahme der Run-Parameter', () => {
  it('reicht Runden/Tage aus der Query als Zahlen an Step3Simulation', () => {
    route.query = { projectId: 'project_42', maxRounds: '7', simulationDays: '2' }

    const step3 = mountSimulation().getComponent({ name: 'Step3Simulation' })

    // Genau hier war der sichtbare Schaden: Step 3 startete stets mit dem
    // Auto-Wert, egal was der Nutzer in Schritt 2 eingestellt hatte.
    expect(step3.props('maxRounds')).toBe(7)
    expect(step3.props('simulationDays')).toBe(2)
  })

  it('laesst die Props leer, wenn nichts uebersteuert wurde', () => {
    route.query = { projectId: 'project_42' }

    const step3 = mountSimulation().getComponent({ name: 'Step3Simulation' })

    // undefined statt 0/null — sonst wuerde eine Null-Runden-Simulation starten.
    expect(step3.props('maxRounds')).toBeUndefined()
    expect(step3.props('simulationDays')).toBeUndefined()
  })

  it('ignoriert unbrauchbare Werte aus manipulierten URLs', () => {
    route.query = { maxRounds: '0', simulationDays: 'abc' }

    const step3 = mountSimulation().getComponent({ name: 'Step3Simulation' })

    expect(step3.props('maxRounds')).toBeUndefined()
    expect(step3.props('simulationDays')).toBeUndefined()
  })

  it('nimmt die Query beim Tab-Wechsel mit', async () => {
    route.query = { projectId: 'project_42', maxRounds: '7' }

    await mountSimulation().getComponent({ name: 'Tabs' }).vm.$emit('update:modelValue', 'feed')

    // Der Tab-Wechsel verlor vorher projectId und Run-Parameter.
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulationFeed',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42', maxRounds: '7' },
    })
  })
})
