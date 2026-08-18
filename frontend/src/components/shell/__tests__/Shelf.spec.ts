/**
 * Shelf — Komponenten-Tests (Block B3).
 *
 * Prueft:
 * 1. Filterpille wechseln loest filterChange mit dem richtigen Filter aus.
 * 2. Klick auf eine Zeile emittiert select mit dem richtigen Objekt.
 * 3. Zeile mit active zeigt den Abbrechen-Knopf, Zeile ohne active nicht.
 * 4. Leere Liste zeigt den Leer-Text (shelf.empty).
 * 5. Pfeiltasten (ArrowDown/ArrowUp) verschieben den Roving-Tabindex.
 * 6. Pause/Resume-Knopf nur bei pausierbarer aktiver Zeile, ruft die Simulation-API.
 * 7. Weiter-Aktion einer Zeile navigiert zum hinterlegten Routenziel.
 * 8. Filter "jobs" rendert die Rohebene als Tabelle statt der Zeilenliste.
 * 9. "Neues Objekt" navigiert zum Dashboard.
 *
 * Selektoren ausschliesslich ueber ShelfTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, ref } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { ShelfTestId } from '../../../contracts/testIds'
import type { ShelfFilter, ShelfJobRow, ShelfObject } from '../../../types/shelf'
import type { useShelf } from '../../../composables/useShelf'

vi.mock('../../../api/runs', () => ({
  cancelRun: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/simulation', () => ({
  pauseSimulation: vi.fn().mockResolvedValue({}),
  resumeSimulation: vi.fn().mockResolvedValue({}),
}))

import { pauseSimulation, resumeSimulation } from '../../../api/simulation'
import { useCancelAction } from '../useCancelAction'
import Shelf from '../Shelf.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/dashboard', name: 'Dashboard', component: { template: '<div/>' } },
    { path: '/runs/:id', name: 'RunDetail', component: { template: '<div/>' } },
  ],
})

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf eins',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: null,
    ...overrides,
  }
}

/** Baut ein Objekt, das dieselbe Form wie ReturnType<typeof useShelf> hat, ohne die echten API-Aufrufe zu machen. */
function makeShelf(objects: ShelfObject[] = [], jobs: ShelfJobRow[] = []): ReturnType<typeof useShelf> {
  const objectsRef = ref<ShelfObject[]>(objects)
  const jobsRef = ref<ShelfJobRow[]>(jobs)
  const filter = ref<ShelfFilter>('alle')
  const loading = ref(false)
  const error = ref('')
  const filtered = computed(() =>
    filter.value === 'alle' || filter.value === 'jobs' ? objectsRef.value : objectsRef.value.filter((o) => o.kind === filter.value),
  )
  const counts = computed(() => {
    const c: Record<string, number> = { alle: objectsRef.value.length, lauf: 0, bericht: 0, personasatz: 0, graph: 0 }
    for (const o of objectsRef.value) c[o.kind] += 1
    return c
  })
  const activeObjects = computed(() => objectsRef.value.filter((o) => o.active !== null))
  return {
    objects: objectsRef,
    jobs: jobsRef,
    filter,
    filtered,
    counts,
    activeObjects,
    loading,
    error,
    reload: vi.fn().mockResolvedValue(undefined),
  }
}

function mountShelf(objects: ShelfObject[] = [], jobs: ShelfJobRow[] = [], selected: ShelfObject | null = null) {
  const shelf = makeShelf(objects, jobs)
  const wrapper = mount(Shelf, {
    props: { shelf, selected },
    global: { plugins: [i18n, router] },
  })
  return { wrapper, shelf }
}

describe('Shelf', () => {
  beforeEach(() => {
    useCancelAction().undo()
  })

  it('Filterpille wechseln loest filterChange mit dem richtigen Filter aus', async () => {
    const { wrapper } = mountShelf([makeObject()])
    const pills = wrapper.findAll(`[data-testid="${ShelfTestId.filterPill}"]`)
    // Reihenfolge folgt FILTER_ORDER: alle, lauf, bericht, personasatz, graph, jobs
    await pills[1].trigger('click')

    expect(wrapper.emitted('filterChange')).toEqual([['lauf']])
  })

  it('Klick auf eine Zeile emittiert select mit dem richtigen Objekt', async () => {
    const obj = makeObject({ id: 'sim_42' })
    const { wrapper } = mountShelf([obj])
    await wrapper.find(`[data-testid="${ShelfTestId.row}"]`).trigger('click')

    expect(wrapper.emitted('select')).toEqual([[obj]])
  })

  it('Zeile mit active zeigt den Abbrechen-Knopf, Zeile ohne active nicht', () => {
    const active = makeObject({ id: 'a', active: { runId: 'run_a', status: 'processing', pausable: false, simulationId: null } })
    const inactive = makeObject({ id: 'b', active: null })
    const { wrapper } = mountShelf([active, inactive])

    const rows = wrapper.findAll(`[data-testid="${ShelfTestId.row}"]`)
    expect(rows[0].find(`[data-testid="${ShelfTestId.rowCancel}"]`).exists()).toBe(true)
    expect(rows[1].find(`[data-testid="${ShelfTestId.rowCancel}"]`).exists()).toBe(false)
  })

  it('leere Liste zeigt den Leer-Text', () => {
    const { wrapper } = mountShelf([])
    expect(wrapper.find(`[data-testid="${ShelfTestId.empty}"]`).exists()).toBe(true)
  })

  it('Pfeiltasten verschieben den Roving-Tabindex zwischen den Zeilen', async () => {
    const { wrapper } = mountShelf([makeObject({ id: 'a' }), makeObject({ id: 'b' }), makeObject({ id: 'c' })])
    const rows = wrapper.findAll(`[data-testid="${ShelfTestId.row}"]`)
    expect(rows[0].attributes('tabindex')).toBe('0')
    expect(rows[1].attributes('tabindex')).toBe('-1')

    await rows[0].trigger('keydown', { key: 'ArrowDown' })

    const rowsAfter = wrapper.findAll(`[data-testid="${ShelfTestId.row}"]`)
    expect(rowsAfter[0].attributes('tabindex')).toBe('-1')
    expect(rowsAfter[1].attributes('tabindex')).toBe('0')

    await rowsAfter[1].trigger('keydown', { key: 'ArrowUp' })
    const rowsBack = wrapper.findAll(`[data-testid="${ShelfTestId.row}"]`)
    expect(rowsBack[0].attributes('tabindex')).toBe('0')
  })

  it('Pause-Knopf ist nur bei pausierbarer aktiver Zeile sichtbar und ruft pauseSimulation', async () => {
    const pausable = makeObject({
      id: 'a',
      active: { runId: 'run_a', status: 'processing', pausable: true, simulationId: 'sim_a' },
    })
    const notPausable = makeObject({
      id: 'b',
      active: { runId: 'run_b', status: 'processing', pausable: false, simulationId: null },
    })
    const { wrapper } = mountShelf([pausable, notPausable])
    const rows = wrapper.findAll(`[data-testid="${ShelfTestId.row}"]`)
    expect(rows[0].find(`[data-testid="${ShelfTestId.rowPause}"]`).exists()).toBe(true)
    expect(rows[1].find(`[data-testid="${ShelfTestId.rowPause}"]`).exists()).toBe(false)

    await rows[0].find(`[data-testid="${ShelfTestId.rowPause}"]`).trigger('click')
    expect(pauseSimulation).toHaveBeenCalledWith('sim_a')
    expect(resumeSimulation).not.toHaveBeenCalled()
  })

  it('Weiter-Aktion navigiert zum hinterlegten Routenziel', async () => {
    const obj = makeObject({
      id: 'a',
      nextAction: { label: 'Weiter', to: { name: 'RunDetail', params: { id: 'run_a' } }, kind: 'accent' },
    })
    const { wrapper } = mountShelf([obj])
    await wrapper.find(`[data-testid="${ShelfTestId.rowNextAction}"]`).trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('RunDetail')
    expect(router.currentRoute.value.params.id).toBe('run_a')
  })

  it('Filter "jobs" rendert die Rohebene als Tabelle statt der Zeilenliste', async () => {
    const job: ShelfJobRow = { runId: 'run_1', runType: 'simulation_run', status: 'processing', message: '', updatedAt: '2026-08-18T10:00:00Z', progress: 40 }
    const { wrapper, shelf } = mountShelf([makeObject()], [job])
    shelf.filter.value = 'jobs'
    await wrapper.vm.$nextTick()

    expect(wrapper.find(`[data-testid="${ShelfTestId.jobsTable}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="${ShelfTestId.row}"]`).exists()).toBe(false)
  })

  it('zeigt in der Jobs-Tabelle bei unbekanntem Status den Rohwert, nicht den i18n-Schluessel', async () => {
    // vue-i18n gibt bei einem fehlenden Schluessel den Schluessel selbst
    // zurueck. Ein Backend-Status, den die Locales noch nicht kennen,
    // darf nicht als „shelf.status.xyz" in der Tabelle stehen.
    const job: ShelfJobRow = {
      runId: 'run_1',
      runType: 'simulation_run',
      status: 'kuenftiger_status' as ShelfJobRow['status'],
      message: '',
      updatedAt: '2026-08-18T10:00:00Z',
      progress: 0,
    }
    const { wrapper, shelf } = mountShelf([makeObject()], [job])
    shelf.filter.value = 'jobs'
    await wrapper.vm.$nextTick()

    const text = wrapper.find(`[data-testid="${ShelfTestId.jobsTable}"]`).text()
    expect(text).toContain('kuenftiger_status')
    expect(text).not.toContain('shelf.status.')
  })

  it('"Neues Objekt" navigiert zum Dashboard', async () => {
    const { wrapper } = mountShelf([])
    await wrapper.find(`[data-testid="${ShelfTestId.newObject}"]`).trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('Dashboard')
  })
})
