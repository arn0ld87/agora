import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../api/simulation', () => ({ createSimulationBranch: vi.fn() }))

import { createSimulationBranch } from '../../api/simulation'
import { useDeriveSimulation } from '../useDeriveSimulation'

describe('useDeriveSimulation', () => {
  beforeEach(() => vi.clearAllMocks())

  it('leitet mit Personas ab und gibt die neue Simulation zurueck', async () => {
    vi.mocked(createSimulationBranch).mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_neu' },
    } as never)

    const { derive } = useDeriveSimulation()
    const res = await derive('sim_alt', '  Zweiter Durchgang  ')

    expect(res).toEqual({ simulationId: 'sim_neu' })
    // Personas werden uebernommen, die Berichtsartefakte nicht: dieselben
    // Personen, eine neue Auswertung.
    expect(createSimulationBranch).toHaveBeenCalledWith('sim_alt', {
      branch_name: 'Zweiter Durchgang',
      copy_profiles: true,
      copy_report_artifacts: false,
    })
  })

  it('verweigert ohne Quell-Simulation oder Namen, ohne die API zu rufen', async () => {
    const { derive, error } = useDeriveSimulation()

    expect(await derive('', 'Name')).toBeNull()
    expect(await derive('sim_alt', '   ')).toBeNull()
    expect(createSimulationBranch).not.toHaveBeenCalled()
    expect(error.value).toBe('missing_input')
  })

  it('meldet einen Fehlschlag, statt eine Simulation vorzutaeuschen', async () => {
    vi.mocked(createSimulationBranch).mockResolvedValue({ success: true, data: {} } as never)

    const { derive, error } = useDeriveSimulation()
    expect(await derive('sim_alt', 'Ohne ID')).toBeNull()
    expect(error.value).toBe('no_simulation_id')
  })

  it('faengt einen Netzwerkfehler ab und haelt seine Meldung fest', async () => {
    vi.mocked(createSimulationBranch).mockRejectedValue(new Error('Verbindung weg'))

    const { derive, error, busy } = useDeriveSimulation()
    expect(await derive('sim_alt', 'Neuer Lauf')).toBeNull()
    expect(error.value).toBe('Verbindung weg')
    expect(busy.value).toBe(false)
  })

  it('setzt busy waehrend des Laufs und danach zurueck', async () => {
    let aufloesen: (v: unknown) => void = () => {}
    vi.mocked(createSimulationBranch).mockReturnValue(
      new Promise((r) => { aufloesen = r }) as never,
    )

    const { derive, busy } = useDeriveSimulation()
    const p = derive('sim_alt', 'Neuer Lauf')
    expect(busy.value).toBe(true)

    aufloesen({ success: true, data: { simulation_id: 'sim_neu' } })
    await p
    expect(busy.value).toBe(false)
  })
})
