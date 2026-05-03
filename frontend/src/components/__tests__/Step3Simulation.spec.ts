/**
 * Step3Simulation — Component-Mount-Smoketest (Aktion 7 aus
 * docu/2026-05-03-frontend-crash-step3-tdz-stalecode-arbeitsprotokoll.md).
 *
 * Hintergrund: Der TDZ-Bug aus PR #207 (`Cannot access 'consoleLogs' before
 * initialization`) brach das Component-Setup *zur Mount-Zeit*. Diese Suite
 * mountet Step3Simulation gegen einen minimalen Stub und prüft, dass kein
 * ReferenceError fliegt — würde der Watcher-Getter wieder vor der Composable-
 * Init stehen, schlüge der Test fehl, bevor der User je den weissen
 * Bildschirm sieht.
 *
 * Bewusst smoketest, nicht Verhaltenstest: Wir validieren Setup-Reihenfolge,
 * nicht Watcher-Logik. Letzteres deckt das eigene Test-Set für
 * useIncrementalLogPolling ab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'

// localStorage muss vor allen Modul-Imports gemockt sein,
// da i18n/index.js bei Import-Zeit localStorage.getItem aufruft.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

vi.mock('../../api/simulation', () => ({
  startSimulation: vi.fn(),
  stopSimulation: vi.fn(),
  pauseSimulation: vi.fn(),
  resumeSimulation: vi.fn(),
  getRunStatus: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getRunStatusDetail: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getSimulationConsoleLog: vi.fn().mockResolvedValue({ success: true, data: { lines: [], next_cursor: 0 } }),
}))
vi.mock('../../api/report', () => ({
  generateReport: vi.fn(),
}))

// SSE/EventSource im Test-Env nicht verfuegbar — neutralisieren.
vi.mock('../../composables/useEventStream', () => ({
  useEventStream: () => ({
    connected: { value: false },
    close: () => {},
  }),
}))

import Step3Simulation from '../Step3Simulation.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  // missingWarn: false, um Mock-i18n nicht zu vergiften — Smoketest, keine
  // Übersetzungs-Vollständigkeit.
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/simulation/:simulationId', name: 'Simulation', component: { template: '<div/>' } },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div/>' } },
  ],
})

const globalStubs = {
  Btn: { template: '<button><slot /></button>' },
  Badge: { template: '<span><slot /></span>' },
  Kicker: { template: '<span><slot /></span>' },
  StickyScrollBanner: { template: '<div/>' },
}

function mountComponent() {
  return mount(Step3Simulation, {
    props: {
      simulationId: 'sim_test_smoke',
      maxRounds: 5,
      simulationDays: 1,
      minutesPerRound: 30,
      projectData: { name: 'smoketest' },
      graphData: { nodes: [], edges: [] },
      systemLogs: [],
    },
    global: {
      plugins: [router, i18n],
      stubs: globalStubs,
    },
  })
}

describe('Step3Simulation — mount smoketest (Aktion 7, PR #207-Followup)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne TDZ-Error (consoleLogs darf nicht vor Init referenziert werden)', () => {
    // Wenn watch() vor der useIncrementalLogPolling-Destrukturierung steht,
    // wirft der Watcher-Getter beim Setup einen ReferenceError. Dieser Mount
    // ist die einfachste Reproduktion des Original-Bugs.
    const errors: unknown[] = []
    const errSpy = vi.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args)
    })

    expect(() => mountComponent()).not.toThrow()

    const tdzMatches = errors.filter((args) =>
      JSON.stringify(args).includes('before initialization'),
    )
    expect(tdzMatches).toEqual([])

    errSpy.mockRestore()
  })

  it('rendert Setup vollständig (Wrapper hat eine Wurzel)', () => {
    const wrapper = mountComponent()
    expect(wrapper.element).toBeTruthy()
    // Wenn Setup throwt, hat Wrapper keinen sinnvollen DOM — exists() reicht.
    expect(wrapper.exists()).toBe(true)
  })
})
