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

// Budget, wie HeroNewRun es aufbaut — inkl. der Schema-Defaults, die
// RunBudgetConfigSchema beim Parsen setzt.
const DASHBOARD_BUDGET = {
  schema_version: 1,
  enforcement: 'hard',
  currency: 'USD',
  max_tokens: 5000,
}

/** Query der letzten Navigation. Das Budget wird als JSON verglichen, nicht als String — die Schluesselreihenfolge gehoert dem Zod-Schema. */
function pushedQuery(): Record<string, unknown> {
  const call = routerPush.mock.calls.at(-1)?.[0] as { query?: Record<string, unknown> }
  return call?.query ?? {}
}

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
          props: ['simulationId', 'maxRounds', 'simulationDays', 'budget'],
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

// Regressionstest fuer #1234: Rundenzahl und Budget aus dem Dashboard-Start
// erreichten Schritt 3 nie. Sie reisten ueber den pendingUpload-Store, den
// Schritt 1 nach dem Ontologie-Upload leert — Schritt 3 las anschliessend den
// Reset-Default 10 und gar kein Budget. Nicht erst nach einem Reload, sondern
// im normalen Durchlauf.
describe('Dashboard -> Schritt 3: Uebergabe ueber Schritt 2 hinweg', () => {
  it('erbt die Dashboard-Werte, laesst aber eine Eingabe in Schritt 2 gewinnen', async () => {
    route.query = {
      projectId: 'project_42',
      maxRounds: '25',
      budget: JSON.stringify(DASHBOARD_BUDGET),
    }

    await mountEnvSetup()
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x' })

    expect(pushedQuery().maxRounds).toBe('25')

    await mountEnvSetup()
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x', maxRounds: 7 })

    // Schritt 2 kennt das Budget nicht und darf es deshalb auch nicht
    // verlieren — nur die Rundenzahl wird ueberschrieben.
    const query = pushedQuery()
    expect(query.projectId).toBe('project_42')
    expect(query.maxRounds).toBe('7')
    expect(JSON.parse(String(query.budget))).toEqual(DASHBOARD_BUDGET)
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

  it('reicht das Run-Budget aus der Query als Objekt an Step3Simulation', () => {
    route.query = { projectId: 'project_42', budget: JSON.stringify(DASHBOARD_BUDGET) }

    const step3 = mountSimulation().getComponent({ name: 'Step3Simulation' })

    expect(step3.props('budget')).toEqual(DASHBOARD_BUDGET)
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
