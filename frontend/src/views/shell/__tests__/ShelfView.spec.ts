/**
 * ShelfView — Komponenten-Tests (Block B3).
 *
 * Prueft:
 * 1. Beim Mounten wird die Ablage genau einmal geladen (shelf.reload via useShelf).
 * 2. Route-Param /ablage/lauf/sim_1 waehlt das passende Objekt aus — `selected`
 *    ist ein reiner computed aus der Route, kein eigener synchronisierter Ref.
 * 3. Ein unbekannter Routen-Parameter fuehrt zu selected=null (Leer-Hinweis im Dossier).
 * 4. Klick auf eine Ablage-Zeile navigiert zur passenden Route und aktualisiert das Dossier.
 *
 * Alle vier Datenquellen von useShelf (api/runs, api/report, api/graph,
 * api/simulation) sind gemockt — keine echten Netzwerkaufrufe.
 *
 * Selektoren ausschliesslich ueber ShelfTestId/DossierTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { DossierTestId, ShelfTestId } from '../../../contracts/testIds'
import type { RunDetail } from '../../../contracts/runsContract'

vi.mock('../../../api/runs', () => ({
  listRuns: vi.fn(),
  cancelRun: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/report', () => ({
  listReports: vi.fn().mockResolvedValue({ data: [] }),
}))
vi.mock('../../../api/graph', () => ({
  listProjects: vi.fn().mockResolvedValue({ data: [] }),
}))
vi.mock('../../../api/simulation', () => ({
  listPersonaTemplates: vi.fn().mockResolvedValue({ success: true, data: { count: 0, templates: [] } }),
  pauseSimulation: vi.fn().mockResolvedValue({}),
  resumeSimulation: vi.fn().mockResolvedValue({}),
}))
vi.mock('../../../api/status', () => ({
  getSystemStatus: vi.fn().mockResolvedValue({ success: true }),
}))

import { listRuns } from '../../../api/runs'
import { useCancelAction } from '../../../components/shell/useCancelAction'
import ShelfView from '../ShelfView.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

function makeRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    run_id: 'run_1',
    run_type: 'simulation_run',
    entity_id: 'sim_1',
    status: 'processing',
    progress: 40,
    message: '',
    started_at: '2026-08-18T09:00:00Z',
    updated_at: '2026-08-18T09:30:00Z',
    metadata: {},
    linked_ids: { simulation_id: 'sim_1' },
    artifacts: {},
    resume_capability: {},
    summary: { document_name: 'Erster Testlauf' },
    ...overrides,
  } as RunDetail
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ablage', name: 'Shelf', component: ShelfView },
      { path: '/ablage/:kind(lauf|bericht|personasatz|graph)/:objectId', name: 'ShelfObject', component: ShelfView },
      { path: '/dashboard', name: 'Dashboard', component: { template: '<div/>' } },
    ],
  })
}

describe('ShelfView', () => {
  beforeEach(() => {
    vi.mocked(listRuns).mockReset()
    useCancelAction().undo()
  })

  it('laedt die Ablage beim Mounten genau einmal', async () => {
    vi.mocked(listRuns).mockResolvedValue({ data: { runs: [], total: 0, aggregation: null } } as never)
    const router = makeRouter()
    await router.push('/ablage')
    mount(ShelfView, { global: { plugins: [router, i18n, createPinia()] } })
    await flushPromises()

    expect(listRuns).toHaveBeenCalledTimes(1)
  })

  it('Route-Param /ablage/lauf/sim_1 waehlt das passende Objekt aus', async () => {
    vi.mocked(listRuns).mockResolvedValue({
      data: { runs: [makeRun()], total: 1, aggregation: null },
    } as never)
    const router = makeRouter()
    await router.push('/ablage/lauf/sim_1')
    const wrapper = mount(ShelfView, { global: { plugins: [router, i18n, createPinia()] } })
    await flushPromises()

    expect(wrapper.find(`[data-testid="${DossierTestId.title}"]`).text()).toBe('Erster Testlauf')
  })

  it('ein unbekannter Routen-Parameter fuehrt zu selected=null (Uebersichtszustand im Dossier, Redesign PR 3)', async () => {
    vi.mocked(listRuns).mockResolvedValue({
      data: { runs: [makeRun()], total: 1, aggregation: null },
    } as never)
    const router = makeRouter()
    await router.push('/ablage/lauf/unbekannt')
    const wrapper = mount(ShelfView, { global: { plugins: [router, i18n, createPinia()] } })
    await flushPromises()

    expect(wrapper.find(`[data-testid="${DossierTestId.title}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="${DossierTestId.overview}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="${DossierTestId.root}"]`).text()).toContain(
      'Wähle links ein Objekt, um sein Dossier zu öffnen.',
    )
  })

  it('Klick auf eine Ablage-Zeile navigiert und aktualisiert das Dossier', async () => {
    vi.mocked(listRuns).mockResolvedValue({
      data: { runs: [makeRun()], total: 1, aggregation: null },
    } as never)
    const router = makeRouter()
    await router.push('/ablage')
    const wrapper = mount(ShelfView, { global: { plugins: [router, i18n, createPinia()] } })
    await flushPromises()

    expect(wrapper.find(`[data-testid="${DossierTestId.title}"]`).exists()).toBe(false)

    await wrapper.find(`[data-testid="${ShelfTestId.row}"]`).trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('ShelfObject')
    expect(router.currentRoute.value.params).toEqual({ kind: 'lauf', objectId: 'sim_1' })
    expect(wrapper.find(`[data-testid="${DossierTestId.title}"]`).text()).toBe('Erster Testlauf')
  })

  // Redesign PR 8: /ablage?filter=lauf uebernimmt den Filter aus der Query
  // (Audit Zeile 137: „/runs → Redirect /ablage?filter=lauf").
  it('uebernimmt einen gueltigen ?filter= aus der Query', async () => {
    vi.mocked(listRuns).mockResolvedValue({ data: { runs: [], total: 0, aggregation: null } } as never)
    const router = makeRouter()
    await router.push('/ablage?filter=lauf')
    const wrapper = mount(ShelfView, { global: { plugins: [router, i18n, createPinia()] } })
    await flushPromises()

    expect(wrapper.find(`[data-testid="${ShelfTestId.filterPill}"]`).exists()).toBe(true)
    const activePill = wrapper.findAll(`[data-testid="${ShelfTestId.filterPill}"]`).find((p) => p.attributes('aria-selected') === 'true')
    expect(activePill?.text()).toContain('Läufe')
  })

  it('ignoriert einen ungueltigen ?filter= statt zu werfen', async () => {
    vi.mocked(listRuns).mockResolvedValue({ data: { runs: [], total: 0, aggregation: null } } as never)
    const router = makeRouter()
    await router.push('/ablage?filter=unbekannt')

    // Direkt awaiten statt in expect(async () => …).not.toThrow() zu wickeln:
    // toThrow ist synchron, ruft die Funktion auf, sieht ein Promise statt
    // eines Wurfs und ist zufrieden — die Zusicherung im Rumpf waere nie
    // ausgewertet worden und ein Fehlschlag nur eine unbehandelte Rejection.
    const wrapper = mount(ShelfView, { global: { plugins: [router, i18n, createPinia()] } })
    await flushPromises()

    const activePill = wrapper.findAll(`[data-testid="${ShelfTestId.filterPill}"]`).find((p) => p.attributes('aria-selected') === 'true')
    expect(activePill?.text()).toContain('Alle')
  })
})
