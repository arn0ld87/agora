/**
 * useCancelAction — Unit-Tests (Block B3).
 *
 * Prueft:
 * 1. cancel() startet das 5s-Undo-Fenster mit korrektem Countdown.
 * 2. Laeuft das Fenster ab, ruft es cancelRun() auf und zeigt danach
 *    kurz die Bestaetigung (confirmed), die anschliessend wieder verschwindet.
 * 3. undo() vor Ablauf verhindert den API-Aufruf.
 * 4. Ein neuer cancel() ersetzt einen noch laufenden — kein API-Aufruf fuer den alten.
 * 5. pause()/resume() rufen die Simulation-API sofort, ohne Undo-Fenster.
 *
 * useCancelAction haelt seinen State im Modul-Scope (Singleton fuer die
 * ganze Shell). Damit die Tests sich nicht gegenseitig beeinflussen,
 * importiert jeder Test das Modul frisch (vi.resetModules() + dynamic import).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('../../../api/runs', () => ({
  cancelRun: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/simulation', () => ({
  pauseSimulation: vi.fn().mockResolvedValue({}),
  resumeSimulation: vi.fn().mockResolvedValue({}),
}))

import { cancelRun } from '../../../api/runs'
import { pauseSimulation, resumeSimulation } from '../../../api/simulation'

async function freshCancelAction() {
  const mod = await import('../useCancelAction')
  return mod.useCancelAction()
}

describe('useCancelAction', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    vi.resetModules()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('cancel() startet das Undo-Fenster und zaehlt die Sekunden herunter', async () => {
    const cancelAction = await freshCancelAction()
    cancelAction.cancel('run_1')
    expect(cancelAction.pending.value).toEqual({ runId: 'run_1', secondsLeft: 5 })

    vi.advanceTimersByTime(2000)
    expect(cancelAction.pending.value?.secondsLeft).toBe(3)
  })

  it('ruft nach Ablauf des Fensters cancelRun auf und blendet die Bestaetigung nach 3s wieder aus', async () => {
    const cancelAction = await freshCancelAction()
    cancelAction.cancel('run_1')

    await vi.advanceTimersByTimeAsync(5000)
    expect(cancelRun).toHaveBeenCalledWith('run_1')
    expect(cancelAction.pending.value).toBeNull()
    expect(cancelAction.confirmed.value).toBe('run_1')

    await vi.advanceTimersByTimeAsync(3000)
    expect(cancelAction.confirmed.value).toBeNull()
  })

  it('undo() vor Ablauf verhindert den API-Aufruf', async () => {
    const cancelAction = await freshCancelAction()
    cancelAction.cancel('run_1')
    vi.advanceTimersByTime(2000)

    cancelAction.undo()
    expect(cancelAction.pending.value).toBeNull()

    await vi.advanceTimersByTimeAsync(5000)
    expect(cancelRun).not.toHaveBeenCalled()
  })

  it('ein cancel() fuer einen ZWEITEN Lauf fuehrt den ersten sofort aus, statt ihn zu verwerfen', async () => {
    // Es gibt nur einen Undo-Toast. Der erste Abbruch darf dadurch
    // nicht verlorengehen: der Nutzer hat ihn ausgeloest und wuerde
    // nie erfahren, dass er nie passiert ist.
    const cancelAction = await freshCancelAction()
    cancelAction.cancel('run_a')
    vi.advanceTimersByTime(2000)

    cancelAction.cancel('run_b')
    await Promise.resolve()

    expect(cancelAction.pending.value?.runId).toBe('run_b')
    expect(cancelRun).toHaveBeenCalledWith('run_a')

    await vi.advanceTimersByTimeAsync(5000)
    expect(cancelRun).toHaveBeenCalledWith('run_b')
    expect(cancelRun).toHaveBeenCalledTimes(2)
  })

  it('ein erneutes cancel() fuer DENSELBEN Lauf verlaengert nur das Fenster', async () => {
    const cancelAction = await freshCancelAction()
    cancelAction.cancel('run_a')
    vi.advanceTimersByTime(2000)
    cancelAction.cancel('run_a')
    await Promise.resolve()

    expect(cancelRun).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(5000)
    expect(cancelRun).toHaveBeenCalledTimes(1)
    expect(cancelRun).toHaveBeenCalledWith('run_a')
  })

  it('pause()/resume() rufen die Simulation-API sofort auf, ohne Undo-Fenster zu starten', async () => {
    const cancelAction = await freshCancelAction()

    await cancelAction.pause('sim_1')
    expect(pauseSimulation).toHaveBeenCalledWith('sim_1')
    expect(cancelAction.pending.value).toBeNull()

    await cancelAction.resume('sim_1')
    expect(resumeSimulation).toHaveBeenCalledWith('sim_1')
  })
})
