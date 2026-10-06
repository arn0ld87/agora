import { beforeEach, describe, expect, it, vi } from 'vitest'
import { writePendingRunParams, readPendingRunParams } from '@/composables/new-run/pendingRunParams'

const h_ = vi.hoisted(() => ({
  startSimulation: vi.fn(),
  stopSimulation: vi.fn(),
  pauseSimulation: vi.fn(),
  resumeSimulation: vi.fn(),
  cancelRun: vi.fn(),
  resolveRunModel: vi.fn(),
  clearRunModelOverride: vi.fn(),
  getRunModelOverride: vi.fn(),
  defaults: { hasLoadedOnce: true, load: vi.fn(), effectiveRouteForStage: vi.fn() },
}))

vi.mock('@/api/simulation', () => ({
  startSimulation: h_.startSimulation,
  stopSimulation: h_.stopSimulation,
  pauseSimulation: h_.pauseSimulation,
  resumeSimulation: h_.resumeSimulation,
}))
vi.mock('@/api/runs', () => ({ cancelRun: h_.cancelRun }))
vi.mock('@/composables/useRunModelResolver', () => ({
  useRunModelResolver: () => ({ resolveRunModel: h_.resolveRunModel }),
}))
vi.mock('@/store/runModelOverride', () => ({
  clearRunModelOverride: h_.clearRunModelOverride,
  getRunModelOverride: h_.getRunModelOverride,
}))
vi.mock('@/store/aiModels', () => ({ useLlmRoutingDefaultsStore: () => h_.defaults }))

import { useSimulationControl } from '../useSimulationControl'

const SIM = 'sim_0123456789ab'
const ok = (data: unknown = {}) => ({ success: true, data })

beforeEach(() => {
  vi.clearAllMocks()
  window.sessionStorage.clear()
  h_.resolveRunModel.mockResolvedValue({ ref: null, usedRunOverride: false })
  h_.getRunModelOverride.mockReturnValue(null)
  h_.defaults.hasLoadedOnce = true
  h_.defaults.effectiveRouteForStage.mockReturnValue({ model: 'std-model' })
})

describe('useSimulationControl.start', () => {
  it('sendet die Bestandsfelder und nutzt die vorgemerkten Startwerte, danach werden sie geleert', async () => {
    const budget = { schema_version: 1 as const, max_tokens: 1000, enforcement: 'soft' as const, currency: 'USD' }
    writePendingRunParams(SIM, { maxRounds: 24, simulationDays: 1, budget })
    h_.resolveRunModel.mockResolvedValue({
      ref: { provider_connection_id: 'conn_1', model_id: 'm-1', source: 'run-override' },
      usedRunOverride: true,
    })
    h_.startSimulation.mockResolvedValue(ok({ simulation_id: SIM, run_id: 'run_0123456789ab' }))

    const control = useSimulationControl(() => SIM)
    const res = await control.start()

    expect(res).toEqual({ runId: 'run_0123456789ab' })
    expect(h_.startSimulation).toHaveBeenCalledWith({
      simulation_id: SIM,
      platform: 'parallel',
      enable_graph_memory_update: false,
      max_rounds: 24,
      simulation_days: 1,
      budget,
      ai_model_ref: { provider_connection_id: 'conn_1', model_id: 'm-1', source: 'run-override' },
    })
    expect(h_.clearRunModelOverride).toHaveBeenCalledTimes(1)
    expect(readPendingRunParams(SIM)).toBeNull()
    expect(control.error.value).toBeNull()
    expect(control.busy.value).toBeNull()
  })

  it('lässt max_rounds, simulation_days, budget und ai_model_ref ohne Vormerkung und ohne Modell weg', async () => {
    h_.startSimulation.mockResolvedValue(ok({ simulation_id: SIM }))
    const control = useSimulationControl(() => SIM)
    const res = await control.start()

    expect(res).toEqual({ runId: null })
    expect(h_.startSimulation).toHaveBeenCalledWith({
      simulation_id: SIM,
      platform: 'parallel',
      enable_graph_memory_update: false,
    })
    expect(h_.clearRunModelOverride).not.toHaveBeenCalled()
  })

  it('reicht den Backend-Fehlertext (Budget, Rate-Limit) unverändert durch und behält Startwerte und Override', async () => {
    writePendingRunParams(SIM, { maxRounds: 10, simulationDays: null, budget: null })
    h_.resolveRunModel.mockResolvedValue({
      ref: { provider_connection_id: 'conn_1', model_id: 'm-1', source: 'run-override' },
      usedRunOverride: true,
    })
    h_.startSimulation.mockResolvedValue({ success: false, error: 'BudgetExceededError: Kostenbudget erschöpft' })

    const control = useSimulationControl(() => SIM)
    const res = await control.start()

    expect(res).toBeNull()
    expect(control.error.value).toBe('BudgetExceededError: Kostenbudget erschöpft')
    expect(readPendingRunParams(SIM)).not.toBeNull()
    expect(h_.clearRunModelOverride).not.toHaveBeenCalled()
    expect(control.busy.value).toBeNull()
  })

  it('zeigt geworfene Fehler (z. B. ApiError) und meldet Vertragsbruch der Antwort', async () => {
    const control = useSimulationControl(() => SIM)
    h_.startSimulation.mockRejectedValueOnce(new Error('Rate-Limit des Anbieters'))
    expect(await control.start()).toBeNull()
    expect(control.error.value).toBe('Rate-Limit des Anbieters')

    h_.startSimulation.mockResolvedValueOnce(ok({ run_id: 42 }))
    expect(await control.start()).toBeNull()
    expect(control.error.value).toContain('Vertragsbruch')
  })

  it('startet nicht doppelt, solange eine Aktion läuft', async () => {
    let release!: (v: unknown) => void
    h_.startSimulation.mockReturnValue(new Promise((r) => { release = r }))
    const control = useSimulationControl(() => SIM)
    const first = control.start()
    expect(control.busy.value).toBe('start')
    expect(await control.start()).toBeNull()
    release(ok({}))
    await first
    expect(h_.startSimulation).toHaveBeenCalledTimes(1)
  })
})

describe('useSimulationControl Steuerung', () => {
  it('stoppt, pausiert, setzt fort und bricht ab mit den Bestandsaufrufen', async () => {
    h_.stopSimulation.mockResolvedValue(ok())
    h_.pauseSimulation.mockResolvedValue(ok())
    h_.resumeSimulation.mockResolvedValue(ok())
    h_.cancelRun.mockResolvedValue(ok())
    const control = useSimulationControl(() => SIM)

    expect(await control.stop()).toBe(true)
    expect(h_.stopSimulation).toHaveBeenCalledWith({ simulation_id: SIM })
    expect(await control.pause()).toBe(true)
    expect(h_.pauseSimulation).toHaveBeenCalledWith(SIM)
    expect(await control.resume()).toBe(true)
    expect(h_.resumeSimulation).toHaveBeenCalledWith(SIM)
    expect(await control.cancel()).toBe(true)
    expect(h_.cancelRun).toHaveBeenCalledWith(SIM)
  })

  it('meldet success=false und Netzfehler als error und gibt false zurück', async () => {
    const control = useSimulationControl(() => SIM)
    h_.stopSimulation.mockResolvedValue({ success: false, error: 'Kein laufender Prozess' })
    expect(await control.stop()).toBe(false)
    expect(control.error.value).toBe('Kein laufender Prozess')

    h_.pauseSimulation.mockRejectedValue(new Error('offline'))
    expect(await control.pause()).toBe(false)
    expect(control.error.value).toBe('offline')
    expect(control.busy.value).toBeNull()
  })
})

describe('useSimulationControl.plannedModel', () => {
  it('nimmt den Run-Override vor dem Routing-Standard', () => {
    const control = useSimulationControl(() => SIM)
    expect(control.plannedModel()).toBe('std-model')
    h_.getRunModelOverride.mockReturnValue({ provider_connection_id: 'c', model_id: 'override-model', source: 'run-override' })
    expect(control.plannedModel()).toBe('override-model')
  })

  it('liefert null, solange der Standard nicht geladen ist', () => {
    h_.defaults.hasLoadedOnce = false
    const control = useSimulationControl(() => SIM)
    expect(control.plannedModel()).toBeNull()
  })
})
