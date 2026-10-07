/**
 * useLibraryCounts (#1795) — Zaehler der Seitenleiste.
 *
 * Prueft die reine Ableitung (welche Status zaehlen wofuer, „unbekannt“ statt
 * „0“) und das Ladeverhalten (kein zweiter Ladevorgang, solange die Ablage offen ist).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'
import type { ShelfObject, ShelfSource } from '@/types/shelf'

const listRuns = vi.fn()
const listReports = vi.fn()
const listProjects = vi.fn()
const listPersonaTemplates = vi.fn()
vi.mock('@/api/runs', () => ({ listRuns: (...a: unknown[]) => listRuns(...a) }))
vi.mock('@/api/report', () => ({ listReports: (...a: unknown[]) => listReports(...a) }))
vi.mock('@/api/graph', () => ({ listProjects: (...a: unknown[]) => listProjects(...a) }))
vi.mock('@/api/simulation', () => ({ listPersonaTemplates: (...a: unknown[]) => listPersonaTemplates(...a) }))
const listPersonaSets = vi.fn()
vi.mock('@/api/personaSets', () => ({ listPersonaSets: (...a: unknown[]) => listPersonaSets(...a) }))

import {
  deriveLibraryCounts,
  latestSimulationId,
  useLibraryCounts,
} from '../useLibraryCounts'
import { useShellStore } from '@/stores/shell'

function lauf(id: string, status: string, opts: { reason?: string; sim?: string; jobs?: number } = {}): ShelfObject {
  const jobs = Array.from({ length: opts.jobs ?? 1 }, (_, i) => ({
    runId: `run_${id}_${i}`,
    runType: 'simulation_run',
    status: i === 0 ? status : 'completed',
    message: '',
    updatedAt: '2026-10-06T10:00:00Z',
    terminationReason: i === 0 ? (opts.reason ?? null) : null,
    linkedIds: opts.sim ? { simulation_id: opts.sim } : {},
  }))
  return {
    kind: 'lauf', id, title: id, statusLine: '', updatedAt: '', metaId: id,
    nextAction: null, active: null, jobs,
  }
}

function bericht(id: string, simulationId: string | null, reportStatus: string): ShelfObject {
  return {
    kind: 'bericht', id, title: id, statusLine: '', updatedAt: '', metaId: id,
    simulationId, reportStatus, nextAction: null, active: null,
  }
}

function other(kind: 'graph' | 'personasatz', id: string): ShelfObject {
  return { kind, id, title: id, statusLine: '', updatedAt: '', metaId: id, nextAction: null, active: null }
}

const snap = (objects: ShelfObject[], unavailable: ShelfSource[] = []) => ({ objects, unavailable })

describe('deriveLibraryCounts', () => {
  it('ohne Ladestand ist alles unbekannt (null), nie 0', () => {
    expect(deriveLibraryCounts(null)).toEqual({
      laeufe: null, graphen: null, personasaetze: null, laeuft: null, brauchtDich: null, aktivitaet: null,
    })
  })

  it('zaehlt Bibliothek und Aktivitaet (Jobs) aus dem Ablage-Stand', () => {
    const c = deriveLibraryCounts(
      snap([lauf('a', 'completed', { jobs: 3 }), lauf('b', 'completed'), other('graph', 'g'), other('personasatz', 'p1'), other('personasatz', 'p2')]),
      5,
    )
    // Personasaetze: die Zahl der Saetze aus /api/persona-sets, nicht die alten Vorlagen-Zeilen der Ablage.
    expect(c).toMatchObject({ laeufe: 2, graphen: 1, personasaetze: 5, aktivitaet: 4 })
  })

  it('Personasaetze sind ohne bekannte Satzzahl unbekannt (null), auch wenn die Ablage Vorlagen traegt', () => {
    expect(deriveLibraryCounts(snap([other('personasatz', 'p1')])).personasaetze).toBeNull()
    expect(deriveLibraryCounts(null, 4).personasaetze).toBe(4)
  })

  it('„Läuft gerade“ zaehlt nur pending und processing, nicht paused', () => {
    const c = deriveLibraryCounts(
      snap([lauf('a', 'pending'), lauf('b', 'processing'), lauf('c', 'paused'), lauf('d', 'completed')]),
    )
    expect(c.laeuft).toBe(2)
    // paused ist weder „läuft“ noch „braucht dich“: die Zustaende werden nicht zusammengelegt.
    expect(c.brauchtDich).toBe(0)
  })

  it('„Braucht dich“ zaehlt failed, stopped, Budget erschoepft und INCOMPLETE — und sonst nichts', () => {
    const c = deriveLibraryCounts(
      snap([
        lauf('failed', 'failed'),
        lauf('stopped', 'stopped'),
        lauf('budget', 'completed', { reason: 'budget_tokens' }),
        lauf('incomplete', 'completed', { sim: 'sim_inc' }),
        lauf('fine', 'completed', { sim: 'sim_ok' }),
        lauf('running', 'processing'),
        bericht('r1', 'sim_inc', 'incomplete'),
        bericht('r2', 'sim_ok', 'completed'),
      ]),
    )
    expect(c.brauchtDich).toBe(4)
  })

  it('zaehlt einen Lauf mit mehreren Gruenden nur einmal', () => {
    const c = deriveLibraryCounts(
      snap([lauf('x', 'failed', { reason: 'budget_cost', sim: 'sim_x' }), bericht('r', 'sim_x', 'incomplete')]),
    )
    expect(c.brauchtDich).toBe(1)
  })

  it('user_stop ist ein gestoppter Lauf, kein Budgetabbruch', () => {
    const c = deriveLibraryCounts(snap([lauf('s', 'completed', { reason: 'user_stop' })]))
    expect(c.brauchtDich).toBe(0)
  })

  it('ein ausgefallene Quelle macht abhaengige Zahlen unbekannt, die uebrigen bleiben', () => {
    const objects = [lauf('a', 'processing'), other('graph', 'g')]
    expect(deriveLibraryCounts(snap(objects, ['runs']), 0)).toMatchObject({
      laeufe: null, laeuft: null, aktivitaet: null, brauchtDich: null, graphen: null, personasaetze: 0,
    })
    // Berichte fehlen: „unvollstaendig“ laesst sich nicht pruefen — die Zahl waere zu klein.
    expect(deriveLibraryCounts(snap(objects, ['reports']))).toMatchObject({ laeufe: 1, laeuft: 1, brauchtDich: null })
    expect(deriveLibraryCounts(snap(objects, ['projects']))).toMatchObject({ laeufe: 1, graphen: null })
    // Die Vorlagen-Quelle der Ablage beeinflusst die Satzzahl nicht mehr.
    expect(deriveLibraryCounts(snap(objects, ['templates']), 3)).toMatchObject({ laeufe: 1, personasaetze: 3 })
  })
})

describe('latestSimulationId', () => {
  it('liefert die Simulation des ersten (juengsten) Laufs, der eine hat', () => {
    expect(latestSimulationId(snap([lauf('a', 'completed'), lauf('b', 'completed', { sim: 'sim_b' }), lauf('c', 'completed', { sim: 'sim_c' })]))).toBe('sim_b')
  })
  it('null ohne Stand oder ohne Simulation', () => {
    expect(latestSimulationId(null)).toBeNull()
    expect(latestSimulationId(snap([lauf('a', 'completed')]))).toBeNull()
  })
})

describe('useLibraryCounts — Laden', () => {
  const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
  const runsEnvelope = { success: true, data: { runs: [], total: 0, aggregation: null } }

  function mountComposable(router: ReturnType<typeof makeTestRouter>) {
    let api!: ReturnType<typeof useLibraryCounts>
    const wrapper = mount(
      defineComponent({
        setup() {
          api = useLibraryCounts()
          return () => h('div')
        },
      }),
      { global: { plugins: [router, i18n] } },
    )
    return { wrapper, api: () => api }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    listRuns.mockReset().mockResolvedValue(runsEnvelope)
    listReports.mockReset().mockResolvedValue({ success: true, data: [] })
    listProjects.mockReset().mockResolvedValue({ success: true, data: [] })
    listPersonaTemplates.mockReset().mockResolvedValue({ success: true, data: { templates: [] } })
    listPersonaSets.mockReset().mockResolvedValue({ count: 3, sets: [] })
  })

  it('zaehlt Personasaetze aus /api/persona-sets, auch wenn die Laeufe-Bibliothek offen ist', async () => {
    const router = makeTestRouter()
    await router.push({ name: 'LibraryRuns' })
    const { api } = mountComposable(router)
    await flushPromises()
    expect(listPersonaSets).toHaveBeenCalledTimes(1)
    expect(api().counts.value.personasaetze).toBe(3)
    expect(api().loadFailed.value).toBe(false)
  })

  it('laedt die Personasaetze nicht selbst, solange deren Bibliothek offen ist', async () => {
    const router = makeTestRouter()
    await router.push({ name: 'LibraryPersonaSets' })
    const { api } = mountComposable(router)
    await flushPromises()
    expect(listPersonaSets).not.toHaveBeenCalled()
    expect(api().counts.value.personasaetze).toBeNull()
  })

  it('Fehler beim Laden der Personasaetze: Zaehler unbekannt (null), Fehler wird gemeldet', async () => {
    listPersonaSets.mockRejectedValue(new Error('boom'))
    const router = makeTestRouter()
    await router.push('/activity/jobs')
    const { api } = mountComposable(router)
    await flushPromises()
    expect(api().counts.value.personasaetze).toBeNull()
    expect(api().counts.value.laeufe).toBe(0)
    expect(api().loadFailed.value).toBe(true)
  })

  it('laedt beim Einhaengen genau einmal, wenn die Ablage nicht offen ist', async () => {
    const router = makeTestRouter()
    await router.push('/activity/jobs')
    const { api } = mountComposable(router)
    await flushPromises()
    expect(listRuns).toHaveBeenCalledTimes(1)
    expect(listReports).toHaveBeenCalledTimes(1)
    expect(api().counts.value.laeufe).toBe(0)
    expect(api().loadFailed.value).toBe(false)
  })

  it('laedt NICHT, solange die Laeufe-Bibliothek offen ist (LibraryRunsView laedt und veroeffentlicht)', async () => {
    const router = makeTestRouter()
    await router.push({ name: 'LibraryRuns' })
    const { api } = mountComposable(router)
    await flushPromises()
    expect(listRuns).not.toHaveBeenCalled()
    // Noch kein Stand: unbekannt, nicht 0.
    expect(api().counts.value.laeufe).toBeNull()
    // LibraryRunsView veroeffentlicht → die Zaehler folgen ohne eigenen Ladevorgang.
    useShellStore().shelfSnapshot = snap([lauf('a', 'processing')])
    expect(api().counts.value).toMatchObject({ laeufe: 1, laeuft: 1 })
    expect(listRuns).not.toHaveBeenCalled()
  })

  it('laedt einmal, sobald man die Laeufe-Bibliothek verlaesst', async () => {
    const router = makeTestRouter()
    await router.push({ name: 'LibraryRuns' })
    mountComposable(router)
    await flushPromises()
    await router.push('/activity/jobs')
    await flushPromises()
    expect(listRuns).toHaveBeenCalledTimes(1)
  })

  it('faellt eine Quelle aus, bleibt ihr Zaehler leer (null) und der Fehler wird gemeldet', async () => {
    listRuns.mockRejectedValue(new Error('boom'))
    const router = makeTestRouter()
    await router.push('/activity/jobs')
    const { api } = mountComposable(router)
    await flushPromises()
    expect(api().counts.value.laeufe).toBeNull()
    expect(api().counts.value.aktivitaet).toBeNull()
    expect(api().loadFailed.value).toBe(true)
  })
})
