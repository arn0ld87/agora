import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Regressionstest fuer B-09/B-27 und #1234, seit #1801 ueber die vorgemerkten
// Startparameter: Runden/Tage aus Schritt 2 und Budget aus dem Dashboard-Start
// muessen beim Start der Simulation ankommen. Schritt 2 legt sie in
// `pendingRunParams` ab (die Simulation am Lauf liest sie beim Start, siehe
// useSimulationControl.spec) und wechselt dann auf den Feed des Laufs.

const routerPush = vi.fn()
const route: { name: string; query: Record<string, unknown>; params: Record<string, unknown> } = {
  name: 'StepEnvSetup',
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
import { readPendingRunParams, writePendingRunParams } from '@/composables/new-run/pendingRunParams'

const i18nMock = { $t: (key: string) => key }

// Budget, wie HeroNewRun es aufbaut — inkl. der Schema-Defaults, die
// RunBudgetConfigSchema beim Parsen setzt.
const DASHBOARD_BUDGET = {
  schema_version: 1,
  enforcement: 'hard',
  currency: 'USD',
  max_tokens: 5000,
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

const FEED_TARGET = { name: 'RunSimulationFeed', params: { simulationId: 'sim_x' } }

beforeEach(() => {
  setActivePinia(createPinia())
  routerPush.mockClear()
  window.sessionStorage.clear()
  route.query = {}
})

describe('Schritt 2 -> Simulation: Uebergabe der Run-Parameter', () => {
  it('merkt uebersteuerte Runden/Tage vor und wechselt auf den Feed ohne Query', async () => {
    await mountEnvSetup().getComponent({ name: 'Step2EnvSetup' }).vm.$emit('next-step', {
      simulationId: 'sim_x',
      maxRounds: 7,
      simulationDays: 2,
    })

    expect(readPendingRunParams('sim_x')).toEqual({ maxRounds: 7, simulationDays: 2, budget: null })
    expect(routerPush).toHaveBeenCalledWith(FEED_TARGET)
  })

  it('merkt nichts Erfundenes vor, wenn der Nutzer den Auto-Wert nicht anfasst', async () => {
    await mountEnvSetup().getComponent({ name: 'Step2EnvSetup' }).vm.$emit('next-step', { simulationId: 'sim_x' })

    expect(readPendingRunParams('sim_x')).toEqual({ maxRounds: null, simulationDays: null, budget: null })
    expect(routerPush).toHaveBeenCalledWith(FEED_TARGET)
  })

  it('verwirft unbrauchbare Werte (Null-Runden, Tage ausserhalb des Bereichs)', async () => {
    await mountEnvSetup().getComponent({ name: 'Step2EnvSetup' }).vm.$emit('next-step', {
      simulationId: 'sim_x',
      maxRounds: 0,
      simulationDays: 99999,
    })

    expect(readPendingRunParams('sim_x')).toEqual({ maxRounds: null, simulationDays: null, budget: null })
  })
})

describe('Dashboard -> Simulation: Uebergabe ueber Schritt 2 hinweg (#1234)', () => {
  beforeEach(() => {
    route.query = {
      projectId: 'project_42',
      maxRounds: '25',
      budget: JSON.stringify(DASHBOARD_BUDGET),
    }
  })

  it('erbt die Dashboard-Werte aus der Query', async () => {
    await mountEnvSetup().getComponent({ name: 'Step2EnvSetup' }).vm.$emit('next-step', { simulationId: 'sim_x' })

    expect(readPendingRunParams('sim_x')).toEqual({ maxRounds: 25, simulationDays: null, budget: DASHBOARD_BUDGET })
  })

  it('laesst eine Eingabe in Schritt 2 gewinnen und verliert das Budget nicht', async () => {
    await mountEnvSetup()
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x', maxRounds: 7 })

    // Schritt 2 kennt das Budget nicht und darf es deshalb auch nicht verlieren.
    expect(readPendingRunParams('sim_x')).toEqual({ maxRounds: 7, simulationDays: null, budget: DASHBOARD_BUDGET })
  })

  it('ueberschreibt einen frueher vorgemerkten Eintrag nur dort, wo es etwas Neues gibt', async () => {
    route.query = {}
    writePendingRunParams('sim_x', { maxRounds: 12, simulationDays: 3, budget: null })

    await mountEnvSetup()
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x', maxRounds: 7 })

    expect(readPendingRunParams('sim_x')).toEqual({ maxRounds: 7, simulationDays: 3, budget: null })
  })
})
