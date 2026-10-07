/**
 * Lauf aus einem Personasatz ohne Graph (#1807, Etappe 7).
 *
 * Der Weg ist bewusst schmal und eigenstaendig: ein Lauf aus einem Satz geht
 * ueber `create-from-personas` und **nicht** ueber `/simulation/create` mit
 * leerem Graphen. Der Test haelt beides fest — den Endpunkt und das Ausbleiben
 * von `prepare`, weil der Maintainer ausdruecklich entschieden hat, Prepare
 * bleibe unberuehrt. Ohne diese Klausel waere die naechste Aenderung ein
 * „sauberer" Umbau auf den regulaeren Weg, der genau den Graph verlangt, den
 * dieser Lauf nicht hat.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, defineComponent, type App } from 'vue'
import { createI18n } from 'vue-i18n'
import { createRouter, createWebHistory, type Router } from 'vue-router'
import de from '@/i18n/locales/de.json'

const api = vi.hoisted(() => ({
  createSimulation: vi.fn(),
  createSimulationFromPersonas: vi.fn(),
  prepareSimulation: vi.fn(),
}))
const pending = vi.hoisted(() => ({ write: vi.fn() }))

vi.mock('@/api/simulation', async () => {
  const actual = await vi.importActual<typeof import('@/api/simulation')>('@/api/simulation')
  return { ...actual, ...api }
})
vi.mock('../pendingRunParams', () => ({ writePendingRunParams: pending.write }))

import { useNewRunSubmit } from '../useNewRunSubmit'

const INPUT = {
  personaSetId: 'pset_1',
  simulationRequirement: 'Wie hält das Betriebsrat?',
  language: 'de',
  maxRounds: 3,
  simulationDays: 2,
  budget: null,
}

beforeEach(() => {
  for (const f of Object.values(api)) f.mockReset()
  pending.write.mockReset()
})

/**
 * `useI18n` und `useRouter` verlangen einen Vue-Kontext. Deshalb hängt die
 * Composable an eine echte App; die Navigationsziele sind Attrappen, weil
 * dieser Weg nur eine Adresse ansteuert.
 */
function withSetup<T>(composable: () => T): { result: T; app: App; router: Router } {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div/>' } },
      { path: '/simulations/:simulationId', name: 'RunOverview', component: { template: '<div/>' } },
    ],
  })
  // `mounted` trennt „noch nicht gelaufen" von „gelaufen, aber nichts
  // zurueckgegeben" — ohne das waere `result as T` eine Behauptung.
  let result: T | undefined
  let mounted = false
  const app = createApp(
    defineComponent({
      setup() {
        result = composable()
        mounted = true
        return () => null
      },
    }),
  )
  app.use(i18n)
  app.use(router)
  app.mount(document.createElement('div'))
  app.unmount()
  if (!mounted || result === undefined) {
    throw new Error('withSetup: die Composable lief nicht im Setup')
  }
  return { result, app, router }
}

describe('useNewRunSubmit.createFromPersonaSet', () => {
  it('geht über create-from-personas und nicht über /simulation/create', async () => {
    api.createSimulationFromPersonas.mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_1', project_id: 'proj_1', persona_count: 3 },
    })
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet(INPUT)

    expect(api.createSimulationFromPersonas).toHaveBeenCalledWith({
      simulation_requirement: INPUT.simulationRequirement,
      persona_set_id: INPUT.personaSetId,
    })
    // Der regulaere Weg verlangt einen Graphen; ihn zu nehmen, waere falsch.
    expect(api.createSimulation).not.toHaveBeenCalled()
  })

  it('ruft kein prepare — der Endpunkt legt den Lauf fertig an', async () => {
    api.createSimulationFromPersonas.mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_1', project_id: 'proj_1', persona_count: 3 },
    })
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet(INPUT)

    // Maintainer-Entscheid 07.10.: „Prepare bleibt unberührt". Ein vorlaufendes
    // prepare wuerde den Satz sperren, bevor der Lauf existiert.
    expect(api.prepareSimulation).not.toHaveBeenCalled()
  })

  it('schreibt die Startwerte wie im Graph-Weg', async () => {
    api.createSimulationFromPersonas.mockResolvedValue({
      success: true,
      data: { simulation_id: 'sim_1', project_id: 'proj_1', persona_count: 3 },
    })
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet({ ...INPUT, maxRounds: 5, simulationDays: 3 })

    expect(pending.write).toHaveBeenCalledWith('sim_1', {
      maxRounds: 5,
      simulationDays: 3,
      budget: null,
    })
  })

  it('meldet einen fehlgeschlagenen Endpunkt, ohne zu navigieren', async () => {
    api.createSimulationFromPersonas.mockResolvedValue({ success: false, error: 'Satz ist gesperrt' })
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet(INPUT)

    expect(s.error.value).toBe('Satz ist gesperrt')
    expect(pending.write).not.toHaveBeenCalled()
  })

  it('lehnt eine leere Fragestellung ab, bevor er den Server fragt', async () => {
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet({ ...INPUT, simulationRequirement: '' })

    // Der Server verlangt die Fragestellung; ein leerer Aufruf waere ein
    // vermeidbarer Fehlversuch mit klarer Ursache.
    expect(s.error.value).toBeTruthy()
    expect(api.createSimulationFromPersonas).not.toHaveBeenCalled()
  })

  it('lehnt eine leere Satz-Kennung ab, bevor er den Server fragt', async () => {
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet({ ...INPUT, personaSetId: '' })

    expect(s.error.value).toBeTruthy()
    expect(api.createSimulationFromPersonas).not.toHaveBeenCalled()
  })

  it('gibt einen belegten Fehler des Servers weiter', async () => {
    // Der Satz koennte zwischen Anzeige und Klick geloescht sein — die Meldung
    // des Servers ist genauer als jede lokale Uebersetzung.
    api.createSimulationFromPersonas.mockRejectedValue(new Error('Persona set not found: pset_x'))
    const s = withSetup(() => useNewRunSubmit()).result
    await s.createFromPersonaSet(INPUT)

    expect(s.error.value).toContain('pset_x')
  })

  it('lässt keinen zweiten Lauf entstehen, solange der erste läuft', async () => {
    let release: () => void = () => {}
    api.createSimulationFromPersonas.mockImplementation(
      () => new Promise((resolve) => {
        release = () => resolve({ success: true, data: { simulation_id: 'sim_1', project_id: 'p', persona_count: 1 } })
      }),
    )
    const s = withSetup(() => useNewRunSubmit()).result
    const first = s.createFromPersonaSet(INPUT)
    await s.createFromPersonaSet(INPUT)
    release()
    await first

    expect(api.createSimulationFromPersonas).toHaveBeenCalledTimes(1)
  })
})
