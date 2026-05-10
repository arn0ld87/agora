/**
 * RunsDashboard — Vitest-Tests (Sub-Slice 28, Issue #63).
 *
 * Prueft:
 * 1. Status-Filter-Pills filtern nach Bucket (Aktiv / Abgeschlossen / Fehlerhaft).
 * 2. Polling ruft listRuns nach Intervall erneut auf.
 * 3. Polling stoppt nach Unmount.
 * 4. Klick auf Run-Row navigiert zur RunDetail-Route.
 * 5. Empty-State wenn keine Runs vorhanden.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'

// localStorage muss vor allen Modul-Imports gemockt sein.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// Mock der Runs-API-Schicht vor Vue-Komponenten-Import.
vi.mock('../../api/runs', () => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  getRunEvents: vi.fn(),
  resumeRun: vi.fn(),
  stopRun: vi.fn(),
}))

import { listRuns } from '../../api/runs'
import RunsDashboard from '../RunsDashboard.vue'

// ---- i18n-Stub ----
const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      common: { refresh: 'Aktualisieren' },
      runs: {
        dashboard: {
          title: 'Runs Dashboard',
          subtitle: 'Live-Übersicht aller Pipeline-Runs',
          filter: {
            all: 'Alle',
            active: 'Aktiv',
            done: 'Abgeschlossen',
            failed: 'Fehlerhaft',
          },
          search_placeholder: 'Suche…',
          live_label: 'Live ({interval}s)',
          empty: 'Keine Runs gefunden.',
          loading: 'Lade Runs…',
          error: 'Fehler beim Laden: {message}',
          columns: {
            status: 'Status',
            type: 'Typ',
            entity: 'Entity',
            started: 'Gestartet',
            progress: 'Fortschritt',
          },
          back_to_dashboard: '← Zurück zum Dashboard',
        },
      },
    },
  },
})

// ---- Router-Stub ----
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/runs', name: 'Runs', component: { template: '<div/>' } },
    { path: '/runs/:id', name: 'RunDetail', component: { template: '<div/>' } },
  ],
})

// ---- Fixtures ----

function makeRun(overrides: Partial<{
  run_id: string
  run_type: string
  entity_id: string
  status: string
  progress: number
  message: string
  started_at: string
  updated_at: string
}>): object {
  return {
    run_id: 'run_test_001',
    run_type: 'simulation_run',
    entity_id: 'sim_test',
    parent_run_id: null,
    status: 'completed',
    progress: 100,
    message: 'Done',
    error: null,
    started_at: '2026-05-05T10:00:00Z',
    updated_at: '2026-05-05T10:01:00Z',
    completed_at: '2026-05-05T10:01:00Z',
    branch_label: null,
    metadata: {},
    linked_ids: {},
    artifacts: {},
    resume_capability: {},
    summary: null,
    ...overrides,
  }
}

/**
 * Baut die Envelope-Struktur, die der axios-Interceptor nach aussen gibt:
 * { success: true, data: { runs: [...], total: N, aggregation: null } }
 * Das useRunsPolling-Composable liest .data heraus und parst mit RunsListResponseSchema.
 */
function makeListResponse(runs: object[]): object {
  return {
    success: true,
    data: {
      runs,
      total: runs.length,
      aggregation: null,
    },
  }
}

const FIVE_RUNS = [
  makeRun({ run_id: 'run_pending',    status: 'pending',    run_type: 'graph_build' }),
  makeRun({ run_id: 'run_processing', status: 'processing', run_type: 'simulation_prepare' }),
  makeRun({ run_id: 'run_completed',  status: 'completed',  run_type: 'report_generate' }),
  makeRun({ run_id: 'run_failed',     status: 'failed',     run_type: 'simulation_run' }),
  makeRun({ run_id: 'run_stopped',    status: 'stopped',    run_type: 'simulation_run' }),
]

// ---- Helper: mount component ----
function mountDashboard(props: { pollIntervalMs?: number } = {}) {
  return mount(RunsDashboard, {
    props: { pollIntervalMs: 5000, ...props },
    global: {
      plugins: [router, i18n],
    },
  })
}

// ---- Tests ----

describe('RunsDashboard (Sub-Slice 28, #63)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // -------------------------------------------------------------------------
  // 1. Filter-Pills filtern nach Status-Bucket
  // -------------------------------------------------------------------------
  it('test_pills_filter_runs_by_status_bucket', async () => {
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock.mockResolvedValue(makeListResponse(FIVE_RUNS))

    const wrapper = mountDashboard()
    await flushPromises()

    // Default: "Alle" — alle 5 Runs sichtbar
    expect(wrapper.findAll('.run-row').length).toBe(5)

    // Klick auf "Aktiv" (pending + processing = 2 Runs)
    const pills = wrapper.findAll('.pill')
    const activePill = pills.find((p) => p.text() === 'Aktiv')
    expect(activePill).toBeDefined()
    await activePill!.trigger('click')
    await wrapper.vm.$nextTick()

    const activeRows = wrapper.findAll('.run-row')
    expect(activeRows.length).toBe(2)

    // Klick auf "Fehlerhaft" (failed + stopped = 2 Runs)
    const failedPill = pills.find((p) => p.text() === 'Fehlerhaft')
    expect(failedPill).toBeDefined()
    await failedPill!.trigger('click')
    await wrapper.vm.$nextTick()

    const failedRows = wrapper.findAll('.run-row')
    expect(failedRows.length).toBe(2)

    // Klick auf "Abgeschlossen" (completed = 1 Run)
    const donePill = pills.find((p) => p.text() === 'Abgeschlossen')
    expect(donePill).toBeDefined()
    await donePill!.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.findAll('.run-row').length).toBe(1)

    wrapper.unmount()
  })

  // -------------------------------------------------------------------------
  // 2. Polling ruft listRuns initial + nach Tick erneut auf
  // -------------------------------------------------------------------------
  it('test_polling_calls_listRuns_every_5s_when_mounted', async () => {
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock.mockResolvedValue(makeListResponse([]))

    const wrapper = mountDashboard()

    // Initialer Tick (immediate: true in start())
    await flushPromises()
    expect(listRunsMock).toHaveBeenCalledTimes(1)

    // Nach 5 s: zweiter Tick
    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(listRunsMock).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })

  it('test_polling_reacts_to_live_interval_prop_changes', async () => {
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock.mockResolvedValue(makeListResponse([]))

    const wrapper = mountDashboard({ pollIntervalMs: 5000 })
    await flushPromises()
    expect(listRunsMock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ pollIntervalMs: 1000 })
    await flushPromises()

    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(listRunsMock).toHaveBeenCalledTimes(2)

    wrapper.unmount()
  })

  // -------------------------------------------------------------------------
  // 3. Polling stoppt nach Unmount
  // -------------------------------------------------------------------------
  it('test_polling_stops_on_unmount', async () => {
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock.mockResolvedValue(makeListResponse([]))

    const wrapper = mountDashboard()
    await flushPromises()

    const callsAfterMount = listRunsMock.mock.calls.length

    wrapper.unmount()

    // Timer vorrücken — nach Unmount sollte kein weiterer Aufruf kommen
    vi.advanceTimersByTime(10000)
    await flushPromises()

    expect(listRunsMock.mock.calls.length).toBe(callsAfterMount)
  })

  // -------------------------------------------------------------------------
  // 4. Klick auf Run-Row navigiert zur RunDetail-Route
  // -------------------------------------------------------------------------
  it('test_click_on_row_navigates_to_detail', async () => {
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock.mockResolvedValue(
      makeListResponse([makeRun({ run_id: 'run_abc123', status: 'completed' })]),
    )

    const pushSpy = vi.spyOn(router, 'push')

    const wrapper = mountDashboard()
    await flushPromises()

    const rowBtn = wrapper.find('.run-row-btn')
    expect(rowBtn.exists()).toBe(true)

    await rowBtn.trigger('click')

    expect(pushSpy).toHaveBeenCalledWith({
      name: 'RunDetail',
      params: { id: 'run_abc123' },
    })

    wrapper.unmount()
    pushSpy.mockRestore()
  })

  // -------------------------------------------------------------------------
  // 5. Empty-State bei leerer Runs-Liste
  // -------------------------------------------------------------------------
  it('test_empty_state_when_no_runs', async () => {
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock.mockResolvedValue(makeListResponse([]))

    const wrapper = mountDashboard()
    await flushPromises()

    const stateMsg = wrapper.find('.state-message')
    expect(stateMsg.exists()).toBe(true)
    expect(stateMsg.text()).toContain('Keine Runs gefunden.')

    wrapper.unmount()
  })
})
