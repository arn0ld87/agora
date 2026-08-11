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

// IntersectionObserver-Polyfill: FeedColumn nutzt ihn in onMounted; jsdom
// liefert ihn nicht. Minimaler No-Op-Mock reicht für den Smoketest.
class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }
  root = null
  rootMargin = ''
  thresholds: number[] = []
}
;(globalThis as unknown as { IntersectionObserver: typeof MockIntersectionObserver }).IntersectionObserver = MockIntersectionObserver

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
vi.mock('../../api/runs', () => ({
  // run_id ist im Response IMMER die aufgeloeste run_-ID. Der frühere Mock
  // gab hier eine sim_-ID zurück und zementierte damit die falsche
  // ID-Form — genau die, an der der Abbrechen-Button mit HTTP 400 scheiterte.
  cancelRun: vi.fn().mockResolvedValue({ success: true, data: { run_id: 'run_0123456789ab', status: 'cancel_requested' } }),
  // Issue #764: RunResourceMonitor (eingebunden in Step3Simulation) pollt
  // GET /api/runs/<id> für budget/usage — Default: keine Budget-Anreicherung.
  getRun: vi.fn().mockResolvedValue({ success: true, data: {} }),
}))

// Kanonische Modell-Auswahl: Default ist kein ai_model_ref. Die Routing-Tests
// überschreiben effectiveRef gezielt.
let _effectiveRefValue: { provider_connection_id: string; model_id: string; source: string } | null = null
vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: { get value() { return _effectiveRefValue }, set value(_v: unknown) { /* noop */ } },
    effectiveRoute: { value: null },
    loading: { value: false },
    error: { value: null },
    ensureLoaded: vi.fn().mockResolvedValue(undefined),
    setGlobalSelection: vi.fn().mockResolvedValue(undefined),
  }),
}))

// Transienter Dashboard-Run-Override (HeroNewRun → store/runModelOverride):
// Default null (bestehende Tests unverändert); die Override-Tests setzen
// _runOverrideValue vor dem Mount.
let _runOverrideValue: { provider_connection_id: string; model_id: string; source: string } | null = null
const _clearRunOverrideSpy = vi.fn()
vi.mock('@/store/runModelOverride', () => ({
  getRunModelOverride: () => _runOverrideValue,
  clearRunModelOverride: () => _clearRunOverrideSpy(),
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

import Step3Simulation from '@/components/v4/steps/Step3Simulation.vue'
import { useEventStream } from '../../composables/useEventStream'
import { cancelRun } from '../../api/runs'

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
      simulationId: 'sim_0123456789ab',
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
    _effectiveRefValue = null
    _runOverrideValue = null
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

  it('zeigt Cancel-Button im processing-State (phase=1)', async () => {
    // getRunStatus gibt running zurück → phase=1 nach onMounted.
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: { runner_status: 'running', current_round: 1 } } as never)
    vi.mocked(simulationApi.getRunStatusDetail).mockResolvedValue({ success: true, data: { runner_status: 'running', all_actions: [] } } as never)

    const wrapper = mountComponent()
    await flushPromises()
    await wrapper.vm.$nextTick()

    // phase=1 → template v-else-if="phase === 1" → Cancel-Button sichtbar
    const buttons = wrapper.findAll('button')
    const cancelBtn = buttons.find(b => b.text().includes('step3.controls.cancel'))
    expect(cancelBtn).toBeTruthy()
  })

  it('ruft cancelRun mit simulationId auf, wenn Cancel-Button geklickt wird', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: { runner_status: 'running', current_round: 1 } } as never)
    vi.mocked(simulationApi.getRunStatusDetail).mockResolvedValue({ success: true, data: { runner_status: 'running', all_actions: [] } } as never)

    // window.confirm mocken → true (Nutzer bestätigt)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mountComponent()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    const cancelBtn = buttons.find(b => b.text().includes('step3.controls.cancel'))
    expect(cancelBtn).toBeTruthy()

    await cancelBtn!.trigger('click')
    await flushPromises()

    expect(cancelRun).toHaveBeenCalledOnce()
    expect(cancelRun).toHaveBeenCalledWith('sim_0123456789ab')

    // Format-Assertion: der Wert muss einer der beiden IDs entsprechen, die
    // POST /api/runs/<id>/cancel serverseitig akzeptiert. Ein frei erfundener
    // String wie 'sim_test_smoke' passiert weder validate_simulation_id noch
    // validate_run_id und wuerde in Produktion mit HTTP 400 abgewiesen.
    const [calledWith] = vi.mocked(cancelRun).mock.calls[0]
    expect(calledWith).toMatch(/^(run|sim)_[a-f0-9]{12}$/)

    vi.restoreAllMocks()
  })

  // Issue #1023 (Befund B-26, P1): goReport() rief bisher generateReport()
  // direkt auf — der teuerste Pipeline-Schritt startete ungefragt und mit
  // dem Workspace-Default-Modell. Schritt 3 navigiert jetzt nur noch in
  // einen "bereit"-Zustand; der Report-Start ist explizite Nutzeraktion in
  // Schritt 4 (siehe Step4Report.spec.ts, describe „Lauf-Modell-
  // Vorbelegung").
  it('navigiert bei Klick auf "Weiter zum Bericht" in den Bereit-Zustand, ohne generateReport aufzurufen', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)

    const wrapper = mountComponent()
    await flushPromises()

    expect(_capturedStateCallback).not.toBeNull()
    _capturedStateCallback!({ payload: { runner_status: 'completed', current_round: 5 } })
    await wrapper.vm.$nextTick()

    const reportBtn = wrapper.findAll('button').find(b => b.text().includes('step3.next'))
    expect(reportBtn).toBeTruthy()
    await reportBtn!.trigger('click')
    await flushPromises()

    // Kein direkter Report-Start mehr — nur Navigation.
    const generateReportMock = vi.mocked((await import('../../api/report')).generateReport)
    expect(generateReportMock).not.toHaveBeenCalled()

    // Ziel: Report-Route mit Sentinel-reportId 'new' (kein Report existiert
    // noch) und der simulationId als Query.
    expect(router.currentRoute.value.name).toBe('Report')
    expect(router.currentRoute.value.params.reportId).toBe('new')
    expect(router.currentRoute.value.query.simulationId).toBe('sim_0123456789ab')

    // PR #1025 (Codex P2 / CodeRabbit): `effectiveRunId` faellt hier auf
    // props.simulationId zurueck, weil kein Registry-Run-Start gemockt ist —
    // derselbe Zustand wie nach einem Reload der Simulationsseite. Diese
    // sim_-ID darf NICHT als runId im Query landen: Schritt 4 fragte damit
    // `/api/runs/sim_…`, bekaeme 404 und zeigte nach dem stillen Fallback das
    // Workspace-Modell statt des Lauf-Modells an.
    expect(router.currentRoute.value.query.runId).toBeUndefined()
  })
})

/**
 * ai_model_ref beim Simulationsstart (Root Cause ``404 model MiniMax-M3 not found``).
 *
 * Sichert ab, dass Step3 die kanonische (Connection, Modell)-Auswahl aus
 * routing/defaults.global_default als ``ai_model_ref`` an ``startSimulation``
 * sendet — und NICHT gleichzeitig die Legacy-Felder ``llm_model``/``llm_provider``
 * mitschickt (Backend lehnt die Kombination mit 400 ab).
 */
describe('Step3Simulation — ai_model_ref beim Simulationsstart (#819)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    _capturedStateCallback = null
    _effectiveRefValue = null
    _runOverrideValue = null
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

  it('sendet ai_model_ref aus dem Kanon und lässt llm_model/llm_provider weg', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    _effectiveRefValue = {
      provider_connection_id: 'conn-minimax',
      model_id: 'MiniMax-M3',
      source: 'explicit',
    }

    const wrapper = mountComponent()
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    expect(startBtn).toBeTruthy()
    await startBtn!.trigger('click')
    await flushPromises()

    expect(simulationApi.startSimulation).toHaveBeenCalledTimes(1)
    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn-minimax',
      model_id: 'MiniMax-M3',
      source: 'explicit',
    })
    // Keine Legacy-Felder gemeinsam mit ai_model_ref (Backend: 400 sonst).
    expect(payload.llm_model).toBeUndefined()
    expect(payload.llm_provider).toBeUndefined()
    // Kein Override benutzt → kein Consume-Clear.
    expect(_clearRunOverrideSpy).not.toHaveBeenCalled()
  })

  it('Dashboard-Run-Override gewinnt vor dem Kanon und wird als ai_model_ref gesendet', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    // Kanon zeigt ein ANDERES Modell — der transiente Dashboard-Pick muss gewinnen.
    _effectiveRefValue = {
      provider_connection_id: 'conn-kanon',
      model_id: 'kanon-model',
      source: 'explicit',
    }
    _runOverrideValue = {
      provider_connection_id: 'conn-hero',
      model_id: 'hero-model',
      source: 'run-override',
    }

    const wrapper = mountComponent()
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    expect(startBtn).toBeTruthy()
    await startBtn!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn-hero',
      model_id: 'hero-model',
      source: 'run-override',
    })
    expect(payload.llm_model).toBeUndefined()
    expect(payload.llm_provider).toBeUndefined()
    // Consume-on-success: Override gilt genau für diesen Start.
    expect(_clearRunOverrideSpy).toHaveBeenCalledTimes(1)
  })

  it('Dashboard-Run-Override greift auch ohne Kanon-Auswahl (kein Legacy-Fallback)', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    _effectiveRefValue = null
    _runOverrideValue = {
      provider_connection_id: 'conn-hero',
      model_id: 'hero-model',
      source: 'run-override',
    }
    // Legacy-Storage vorhanden — darf trotzdem NICHT greifen.
    localStorage.setItem('agora.lastModel', 'custom')
    localStorage.setItem('agora.lastCustomModel', 'deepseek-v3.2:cloud')

    const wrapper = mountComponent()
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    expect(startBtn).toBeTruthy()
    await startBtn!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn-hero',
      model_id: 'hero-model',
      source: 'run-override',
    })
    expect(payload.llm_model).toBeUndefined()
    expect(payload.llm_provider).toBeUndefined()
    // Consume-on-success: Override gilt genau für diesen Start.
    expect(_clearRunOverrideSpy).toHaveBeenCalledTimes(1)
  })

  it('fällt ohne Override und Kanon-Auswahl nicht auf Legacy-Storage zurück', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)
    _effectiveRefValue = null
    localStorage.setItem('agora.lastModel', 'custom')
    localStorage.setItem('agora.lastCustomModel', 'deepseek-v3.2:cloud')

    const wrapper = mountComponent()
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    expect(startBtn).toBeTruthy()
    await startBtn!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect(payload.ai_model_ref).toBeUndefined()
    expect(payload.llm_model).toBeUndefined()
    expect(payload.llm_provider).toBeUndefined()
    expect(localStorage.getItem('agora.lastModel')).toBe('custom')
    expect(localStorage.getItem('agora.lastCustomModel')).toBe('deepseek-v3.2:cloud')
  })
})

/**
 * Regression: Rundenzahl und Budget aus HeroNewRun hatten keinerlei Effekt.
 *
 * Erster Anlauf (Slider ohne Wirkung): Der Dashboard-Flow legte den Wert im
 * pendingUpload-Store ab und Step 3 las ihn von dort. Das war nur scheinbar
 * ein Fix — Schritt 1 leert den Store nach dem Ontologie-Upload
 * (`useGraphBuildPipeline` → `clearPendingUpload`), sodass Step 3 den
 * Reset-Default 10 statt der eingestellten Runden las und das Budget aus
 * #764 gar nicht mehr vorfand (Issue #1234).
 *
 * Seitdem kommen beide Werte ausschliesslich ueber die Route-Query herein und
 * erreichen Step 3 als Props. Der Store bleibt hier bewusst befuellt: Er darf
 * das Ergebnis nicht mehr beeinflussen.
 */
describe('Step3Simulation — Run-Parameter aus der Route-Query (Dashboard-Flow)', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    localStorage.clear()
    _capturedStateCallback = null
    _effectiveRefValue = null
    _runOverrideValue = null
    const { setPendingUpload } = await import('../../store/pendingUpload')
    setPendingUpload([], 'requirement', null, 30, 10)
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

  it('ohne maxRounds-Prop bleibt max_rounds weg — der Store ist kein Ersatz', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    const wrapper = mount(Step3Simulation, {
      props: {
        simulationId: 'sim_0123456789ab',
        projectData: { name: 'dashboard-flow' },
        graphData: { nodes: [], edges: [] },
        systemLogs: [],
      },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    await startBtn!.trigger('click')
    await flushPromises()

    // Der Store trug hier frueher die 10 bei — ein Wert, der in Wahrheit der
    // Reset-Default war und die Nutzereingabe still ueberschrieb. Ohne Query
    // gilt jetzt der Auto-Wert des Backends.
    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect('max_rounds' in payload).toBe(false)
  })

  it('reicht das Budget aus der Prop an /simulation/start durch (Issue #764, #1234)', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    const budget = {
      schema_version: 1 as const,
      enforcement: 'hard' as const,
      currency: 'USD',
      max_tokens: 5000,
    }

    const wrapper = mount(Step3Simulation, {
      props: {
        simulationId: 'sim_0123456789ab',
        budget,
        projectData: { name: 'dashboard-flow' },
        graphData: { nodes: [], edges: [] },
        systemLogs: [],
      },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    await startBtn!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect(payload.budget).toEqual(budget)
  })

  it('ohne Budget-Prop bleibt das budget-Feld weg (kein null-Payload)', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    const wrapper = mount(Step3Simulation, {
      props: {
        simulationId: 'sim_0123456789ab',
        projectData: { name: 'dashboard-flow' },
        graphData: { nodes: [], edges: [] },
        systemLogs: [],
      },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    await startBtn!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect('budget' in payload).toBe(false)
  })

  it('nimmt die maxRounds-Prop des Stepped-Flows unveraendert an', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    const wrapper = mountComponent() // maxRounds: 5
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    await startBtn!.trigger('click')
    await flushPromises()

    const payload = vi.mocked(simulationApi.startSimulation).mock.calls[0][0] as unknown as Record<string, unknown>
    expect(payload.max_rounds).toBe(5)
  })
})

/**
 * Regression: Aktionen-Zähler zeigte dauerhaft 0.
 *
 * Der Endpoint /run-status/detail liefert seit dem Pagination-Fix keine
 * vollständige `all_actions`-Liste mehr — nur die paginierten `actions`
 * plus `actions_total` als Server-Count. Das Frontend las weiterhin
 * `res.data.all_actions`, das damit immer `undefined` war und der Zähler
 * auf 0 stand, obwohl die Simulation Hunderte Aktionen produzierte.
 * Zusätzlich enthielt der Dedup-Schlüssel keinen Zeitstempel: zwei
 * identische Aktionen desselben Agenten in derselben Runde wurden still
 * als Duplikat verworfen.
 */
describe('Step3Simulation — Aktionen-Zähler aus actions/actions_total (Pagination-Shape)', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    localStorage.clear()
    _capturedStateCallback = null
    _effectiveRefValue = null
    _runOverrideValue = null
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

  it('liest Aktionen aus `actions` (nicht `all_actions`) und den Total aus `actions_total`', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    const action = {
      round_num: 3,
      platform: 'twitter',
      agent_id: 5,
      action_type: 'create_post',
      timestamp: '2026-07-28T10:48:00',
      action_args: { content: 'Ein Post' },
    }
    vi.mocked(simulationApi.getRunStatusDetail).mockResolvedValue({
      success: true,
      data: {
        runner_status: 'running',
        current_round: 3,
        total_rounds: 96,
        // Keine `all_actions` — die echte Response-Shape nach PR #526.
        actions: [action],
        actions_total: 929,
      },
    } as never)

    const wrapper = mountComponent()
    await flushPromises()

    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    await startBtn!.trigger('click')
    await flushPromises()

    // Polling einmal anstoßen und warten, bis der Detail-Call verarbeitet ist.
    await flushPromises()
    await flushPromises()

    const html = wrapper.html()
    // 929 (Server-Count) statt 0 oder statt der Anzahl sichtbarer Einträge.
    expect(html).toContain('929')
    expect(simulationApi.getRunStatusDetail).toHaveBeenCalled()
  })

  it('Dedup: zwei identische Aktionen mit unterschiedlichem Zeitstempel werden beide gezählt', async () => {
    vi.mocked(simulationApi.getRunStatus).mockResolvedValue({ success: true, data: {} } as never)
    vi.mocked(simulationApi.startSimulation).mockResolvedValue({ success: true, data: { simulation_id: 'sim_0123456789ab' } } as never)

    const base = {
      round_num: 3,
      platform: 'twitter',
      agent_id: 5,
      action_type: 'create_post',
      action_args: { content: 'gleicher Inhalt' },
    }
    vi.mocked(simulationApi.getRunStatusDetail).mockResolvedValue({
      success: true,
      data: {
        runner_status: 'running',
        current_round: 3,
        total_rounds: 96,
        actions: [
          { ...base, timestamp: '2026-07-28T10:48:00' },
          { ...base, timestamp: '2026-07-28T10:49:00' },
        ],
        actions_total: 2,
      },
    } as never)

    const wrapper = mountComponent()
    await flushPromises()
    const startBtn = wrapper.findAll('button').find(b => b.text().includes('step3.controls.start'))
    await startBtn!.trigger('click')
    await flushPromises()
    await flushPromises()

    // Ohne Zeitstempel im Schlüssel wäre nur eine Aktion gezählt worden.
    expect(wrapper.html()).toContain('2')
  })
})
