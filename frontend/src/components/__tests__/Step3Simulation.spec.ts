/**
 * Step3Simulation — Mount-Smoketest + Phase-Promotion-Tests (Sub-Slice A, #209).
 *
 * Smoketest-Hintergrund: Der TDZ-Bug aus PR #207 (`Cannot access 'consoleLogs'
 * before initialization`) brach das Component-Setup *zur Mount-Zeit*. Diese
 * Suite mountet Step3Simulation gegen einen minimalen Stub und prüft, dass
 * kein ReferenceError fliegt.
 *
 * Phase-Promotion-Tests (#209): Sichert ab, dass der „Weiter zum Bericht"-
 * Button auch dann erscheint, wenn
 * - der letzte SSE-Frame verloren geht (HTTP-Detail-Polling muss phase=2 setzen),
 * - ein SSE-completed-Event synchron eintrifft,
 * - resetState phase auf 0 zurücksetzt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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

// Mutable reference so individual tests can override getRunStatusDetail.
import * as simulationApi from '../../api/simulation'

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

// Captured SSE state-callback — re-assigned per test in describe('phase-promotion').
// The factory uses a shared slot so tests can fire the callback after mount.
let _capturedStateCallback: ((msg: unknown) => void) | null = null

// SSE/EventSource: neutralisieren und start/stop bereitstellen.
// Der Smoketest nutzt nur den Baseline-Return; die Phase-Promotion-Tests
// befüllen _capturedStateCallback via mockImplementation.
vi.mock('../../composables/useEventStream', () => ({
  useEventStream: vi.fn().mockImplementation((_idFn: unknown, handlers: { state?: (msg: unknown) => void }) => {
    if (handlers?.state) {
      _capturedStateCallback = handlers.state
    }
    return {
      isStreaming: { value: false },
      error: { value: null },
      lastEventAt: { value: null },
      start: vi.fn().mockResolvedValue(undefined),
      stop: vi.fn(),
    }
  }),
}))

import Step3Simulation from '../Step3Simulation.vue'
import { useEventStream } from '../../composables/useEventStream'
import { generateReport } from '../../api/report'

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

/**
 * Phase-Promotion-Tests (Sub-Slice A, Issue #209).
 *
 * Sichert ab, dass `phase` auf 2 springt und der „Weiter zum Bericht"-Button
 * erscheint, unabhängig davon, ob die Phase-Promotion via SSE oder via
 * HTTP-Detail-Polling erfolgt.
 */
describe('Step3Simulation — phase promotion (Sub-Slice A, #209)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    _capturedStateCallback = null
    // Reset useEventStream mock zurück auf Standardimplementation.
    ;(useEventStream as ReturnType<typeof vi.fn>).mockImplementation(
      (_idFn: unknown, handlers: { state?: (msg: unknown) => void }) => {
        if (handlers?.state) _capturedStateCallback = handlers.state
        return {
          isStreaming: { value: false },
          error: { value: null },
          lastEventAt: { value: null },
          start: vi.fn().mockResolvedValue(undefined),
          stop: vi.fn(),
        }
      }
    )
  })

  it('zeigt Report-Button, sobald HTTP-Detail-Polling runner_status=completed meldet', async () => {
    vi.useFakeTimers()

    // Erster Aufruf (onMounted pollStatus): runner_status=running → phase=1 → startPolling.
    // getRunStatusDetail: Tick 1 running, Tick 2 completed → phase=2.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: { runner_status: 'running', current_round: 3 } } as any)

    vi.mocked(simulationApi.getRunStatusDetail)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .mockResolvedValueOnce({ success: true, data: { runner_status: 'running', all_actions: [] } } as any)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .mockResolvedValueOnce({ success: true, data: { runner_status: 'completed', current_round: 5, all_actions: [] } } as any)

    const wrapper = mountComponent()
    // Hydration: onMounted pollStatus läuft (runner_status=running → phase=1 → startPolling).
    await flushPromises()

    // Polling-Tick 1 (immediate): running, kein phase-Wechsel.
    await vi.advanceTimersByTimeAsync(100)
    await flushPromises()

    // Polling-Tick 2: 2500 ms später, completed → phase=2.
    await vi.advanceTimersByTimeAsync(2500)
    await flushPromises()

    await wrapper.vm.$nextTick()

    // Im Template: `v-else` (weder phase===0 noch phase===1) rendert den goReport-Btn.
    // Wir suchen nach einem Button, der NICHT „Start" heisst und nicht disabled ist.
    const buttons = wrapper.findAll('button')
    // Der goReport-Btn hat :loading=isGeneratingReport und @click=goReport.
    // Im Stub rendert Btn als <button>; der Start-Button ist bei phase===2 nicht da,
    // dafür der goReport-Button.
    // Prüfung: kein Start-Button, aber ein Report-Button vorhanden.
    const startBtnTexts = buttons.map(b => b.text()).filter(t => t.includes('step3.controls.start'))
    expect(startBtnTexts).toHaveLength(0)

    // Der goReport-Button (v-else im Template) muss vorhanden sein.
    const reportBtnTexts = buttons.map(b => b.text()).filter(t => t.includes('step3.next'))
    expect(reportBtnTexts).toHaveLength(1)

    vi.useRealTimers()
  })

  it('zeigt Report-Button bei SSE-completed-Event', async () => {
    // getRunStatus: kein laufender Run, damit phase=0 bleibt nach onMounted.
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)

    const wrapper = mountComponent()
    await flushPromises()

    // Ausgangszustand: phase=0, Start-Button sichtbar.
    expect(wrapper.findAll('button').map(b => b.text()).some(t => t.includes('step3.controls.start'))).toBe(true)

    // SSE-completed-Event synchron feuern, als wäre der Browser-Stream angekommen.
    // _capturedStateCallback wird im useEventStream-Mock beim Setup befüllt.
    expect(_capturedStateCallback).not.toBeNull()
    _capturedStateCallback!({ payload: { runner_status: 'completed', current_round: 5 } })

    await wrapper.vm.$nextTick()

    // Nach SSE-Event: phase=2, goReport-Button da, Start-Button weg.
    const buttons = wrapper.findAll('button')
    expect(buttons.map(b => b.text()).some(t => t.includes('step3.controls.start'))).toBe(false)
    expect(buttons.map(b => b.text()).some(t => t.includes('step3.next'))).toBe(true)
  })

  it('resetState setzt phase auf 0 zurück (Start-Button wieder sichtbar)', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)

    const wrapper = mountComponent()
    await flushPromises()

    // Phase via SSE auf 2 bringen.
    expect(_capturedStateCallback).not.toBeNull()
    _capturedStateCallback!({ payload: { runner_status: 'completed', current_round: 5 } })
    await wrapper.vm.$nextTick()

    // Verifizieren: goReport-Button ist da.
    expect(wrapper.findAll('button').map(b => b.text()).some(t => t.includes('step3.next'))).toBe(true)

    // resetState via Neustart-Simulation-Flow auslösen: doStart ruft resetState().
    // Wir mocken startSimulation so, dass es fehlschlägt (phase bleibt nicht auf 1),
    // aber resetState() wurde aufgerufen → phase=0.
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: false, error: 'test-reset' } as never)
    const backBtn = wrapper.findAll('button').find(b => b.text().includes('common.back'))
    // Alternativ: goBack-Button. Einfacher ist ein direkter Aufruf via expose.
    // Da die Komponente kein defineExpose hat, testen wir über den Start-Button-Click.
    // Nach doStart mit success=false → startError gesetzt, phase bleibt 0 (resetState ruft phase=0).
    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    // Nach phase=2 ist der Start-Button nicht da — doStart können wir nicht via Btn-Click aufrufen.
    // Wir testen resetState indirekt: SSE-completed → phase=2 → neuer SSE-running → phase=1 →
    // SSE-completed → phase=2, dann emit go-back und erneut mount.
    // Einfachste korrekte Prüfung: nach SSE-failed-Event → phase=2, dann SSE-completed erneut.
    // Stattdessen: SSE-failed → phase=2, dann zurück via SSE-Hydration (phase=0 via resetState).
    // Da resetState() nur durch doStart() aufgerufen wird, simulieren wir doStart über vm.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await (wrapper.vm as any).doStart?.() ?? wrapper.vm.$emit('update-status', 'completed')
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Nach doStart (mit success=false): resetState wurde aufgerufen → phase=0 → Start-Button sichtbar.
    expect(wrapper.findAll('button').map(b => b.text()).some(t => t.includes('step3.controls.start'))).toBe(true)
  })

  it('sendet ein persistiertes Custom-Modell beim Reportstart', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    ;(generateReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { report_id: 'report_test123456' },
    })
    localStorage.setItem('agora.lastModel', 'custom')
    localStorage.setItem('agora.lastCustomModel', 'deepseek-v3.2:cloud')

    const wrapper = mountComponent()
    await flushPromises()

    expect(_capturedStateCallback).not.toBeNull()
    _capturedStateCallback!({ payload: { runner_status: 'completed', current_round: 5 } })
    await wrapper.vm.$nextTick()

    const reportBtn = wrapper.findAll('button').find(b => b.text().includes('step3.next'))
    expect(reportBtn).toBeTruthy()
    await reportBtn!.trigger('click')
    await flushPromises()

    expect(generateReport).toHaveBeenCalledWith({
      simulation_id: 'sim_test_smoke',
      llm_model: 'deepseek-v3.2:cloud',
    })
  })
})
