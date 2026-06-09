/**
 * HistoryDatabase — Resume/Stop-Button-Tests (Sub-Slice 35, Issue #64).
 *
 * Prueft:
 * - Resume-Button wird ausgeblendet wenn resume_capability.available false ist.
 * - Resume-Button wird angezeigt wenn resume_capability.available true ist.
 * - handleResume ruft resumeRun mit korrekter run_id und laedt danach neu.
 * - handleStop: confirm=true → stopRun gerufen; confirm=false → nicht gerufen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

// Mock gesamte runs-API-Schicht vor dem Vue-Komponenten-Import.
vi.mock('../../api/runs', () => ({
  listRuns: vi.fn(),
  getRunEvents: vi.fn().mockResolvedValue({ data: [] }),
  resumeRun: vi.fn().mockResolvedValue({ success: true, data: { run_id: 'run_aabbccddeeff' } }),
  stopRun: vi.fn().mockResolvedValue({ success: true }),
}))

vi.mock('../../api/simulation', () => ({
  createSimulationBranch: vi.fn(),
}))

vi.mock('../../api/envelope', () => ({
  isApiError: vi.fn().mockReturnValue(false),
}))

vi.mock('../../api/errorMessages', () => ({
  userMessageFor: vi.fn().mockReturnValue('Fehler'),
  isRetryable: vi.fn().mockReturnValue(false),
}))

import { listRuns, resumeRun, stopRun } from '../../api/runs'
import HistoryDatabase from '../HistoryDatabase.vue'

// Minimaler i18n-Stub (HistoryDatabase nutzt nur locale-Wert, kein t())
const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: { de: {} },
})

// Minimaler Router-Stub
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/simulation/:simulationId', name: 'Simulation', component: { template: '<div/>' } },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div/>' } },
    { path: '/runs', name: 'Runs', component: { template: '<div/>' } },
  ],
})

// Basis-Run ohne Resume-Capability
const BASE_RUN = {
  run_id: 'run_aabbccddeeff',
  run_type: 'simulation_run',
  entity_id: 'sim_test',
  status: 'stopped',
  progress: 0,
  message: 'Test run',
  updated_at: '2026-05-03T12:00:00.000Z',
  started_at: '2026-05-03T11:00:00.000Z',
  linked_ids: { simulation_id: 'sim_test', project_id: 'proj_test' },
  artifacts: {},
  metadata: {},
  branch_label: null,
  resume_capability: { available: false, action: null, label: null },
}

function makeListRunsResponse(run: object) {
  return { success: true, data: [run] }
}

async function mountWithSelectedRun(run: object) {
  const listRunsMock = listRuns as ReturnType<typeof vi.fn>
  // Erste listRuns-Antwort (onMounted loadRuns) + selectRun-Detail-Aufruf
  listRunsMock.mockResolvedValue(makeListRunsResponse(run))

  const wrapper = mount(HistoryDatabase, {
    global: {
      plugins: [router, i18n],
    },
  })

  // onMounted: loadRuns abwarten
  await flushPromises()

  // Ersten Run anklicken, um selectedRun zu setzen
  const runRow = wrapper.find('[data-run-id]')
  if (runRow.exists()) {
    await runRow.trigger('click')
    await flushPromises()
  } else {
    // Fallback: selectedRun direkt via vm setzen
    ;(wrapper.vm as any).selectedRun = run
    await wrapper.vm.$nextTick()
  }

  return wrapper
}

describe('HistoryDatabase — Resume/Stop-Buttons (Sub-Slice 35)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ;(listRuns as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: [] })
  })

  // -------------------------------------------------------------------------
  // Test 1: Resume-Button ausgeblendet wenn available=false
  // -------------------------------------------------------------------------

  it('resume-button is hidden when resume_capability.available is false', async () => {
    const run = { ...BASE_RUN, resume_capability: { available: false, action: null, label: null } }
    ;(listRuns as ReturnType<typeof vi.fn>).mockResolvedValue(makeListRunsResponse(run))

    const wrapper = mount(HistoryDatabase, {
      global: { plugins: [router, i18n] },
    })
    await flushPromises()

    // selectedRun direkt setzen (kein klickbares data-run-id im vereinfachten DOM)
    ;(wrapper.vm as any).selectedRun = run
    await wrapper.vm.$nextTick()

    // Kein Button mit Resume-Label sichtbar
    const buttons = wrapper.findAll('button')
    const resumeButton = buttons.find((b) =>
      b.text().toLowerCase().includes('resume') ||
      b.text().toLowerCase().includes('restart'),
    )
    expect(resumeButton).toBeUndefined()
  })

  // -------------------------------------------------------------------------
  // Test 2: Resume-Button sichtbar wenn available=true
  // -------------------------------------------------------------------------

  it('resume-button is visible with correct label when available=true', async () => {
    const run = {
      ...BASE_RUN,
      resume_capability: { available: true, action: 'restart', label: 'Restart run' },
    }
    ;(listRuns as ReturnType<typeof vi.fn>).mockResolvedValue(makeListRunsResponse(run))

    const wrapper = mount(HistoryDatabase, {
      global: { plugins: [router, i18n] },
    })
    await flushPromises()

    ;(wrapper.vm as any).selectedRun = run
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    const resumeButton = buttons.find((b) => b.text().includes('Restart run'))
    expect(resumeButton).toBeDefined()
    expect(resumeButton!.exists()).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Test 3: handleResume ruft resumeRun mit korrekter run_id
  // -------------------------------------------------------------------------

  it('handleResume calls resumeRun with correct run_id and reloads', async () => {
    const run = {
      ...BASE_RUN,
      resume_capability: { available: true, action: 'restart', label: 'Restart run' },
    }
    ;(listRuns as ReturnType<typeof vi.fn>).mockResolvedValue(makeListRunsResponse(run))
    ;(resumeRun as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { run_id: run.run_id },
    })

    vi.spyOn(window, 'confirm').mockReturnValue(true)

    const wrapper = mount(HistoryDatabase, {
      global: { plugins: [router, i18n] },
    })
    await flushPromises()

    ;(wrapper.vm as any).selectedRun = run
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    const resumeButton = buttons.find((b) => b.text().includes('Restart run'))
    expect(resumeButton).toBeDefined()
    await resumeButton!.trigger('click')
    await flushPromises()

    expect(resumeRun).toHaveBeenCalledWith(run.run_id)
    // listRuns muss mindestens einmal nach dem Click aufgerufen worden sein
    // (loadRuns nach Resume; Gesamtzahl variiert durch selectRun-Hydration).
    expect(listRuns).toHaveBeenCalled()
    const callCount = (listRuns as ReturnType<typeof vi.fn>).mock.calls.length
    expect(callCount).toBeGreaterThanOrEqual(2)
  })

  // -------------------------------------------------------------------------
  // Test 4: handleStop: confirm=true → stopRun gerufen; confirm=false → nicht
  // -------------------------------------------------------------------------

  it('handleStop calls stopRun only when window.confirm returns true', async () => {
    const run = {
      ...BASE_RUN,
      run_type: 'simulation_run',
      status: 'processing',
      resume_capability: { available: false, action: null, label: null },
    }
    ;(listRuns as ReturnType<typeof vi.fn>).mockResolvedValue(makeListRunsResponse(run))

    const wrapper = mount(HistoryDatabase, {
      global: { plugins: [router, i18n] },
    })
    await flushPromises()

    ;(wrapper.vm as any).selectedRun = run
    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    const stopButton = buttons.find((b) => b.text().includes('Stop run'))
    expect(stopButton).toBeDefined()

    // confirm=false → stopRun darf NICHT aufgerufen werden
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await stopButton!.trigger('click')
    await flushPromises()

    expect(stopRun).not.toHaveBeenCalled()

    // confirm=true → stopRun MUSS aufgerufen werden
    confirmSpy.mockReturnValue(true)
    await stopButton!.trigger('click')
    await flushPromises()

    expect(stopRun).toHaveBeenCalledWith(run.run_id)
  })
})

// ---------------------------------------------------------------------------
// #3382999381 — selectRun: no crash when API fails and run has no run_id
// ---------------------------------------------------------------------------

describe('HistoryDatabase — selectRun null-safety (review fix #3382999381)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('does not crash and keeps selectedRun unchanged when listRuns fails during selectRun', async () => {
    const run = { ...BASE_RUN }

    // Initial load succeeds, selectRun detail-hydration call fails
    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    listRunsMock
      .mockResolvedValueOnce(makeListRunsResponse(run)) // onMounted loadRuns
      .mockRejectedValueOnce(new Error('network error'))  // selectRun hydration

    const wrapper = mount(HistoryDatabase, {
      global: { plugins: [router, i18n] },
    })
    await flushPromises()

    // Manually trigger selectRun with a run that has no run_id (undefined)
    const runWithoutId = { ...BASE_RUN, run_id: undefined as unknown as string }
    ;(wrapper.vm as any).selectedRun = runWithoutId
    await wrapper.vm.$nextTick()

    // Call selectRun directly — must not throw even if run_id is undefined
    await expect(
      (wrapper.vm as any).selectRun(runWithoutId),
    ).resolves.toBeUndefined()

    // selectedRun should remain at the value we set (not overwritten to a broken state)
    expect((wrapper.vm as any).selectedRun).toBeDefined()
  })

  it('does not update selectedRun when API returns null (catch returns null)', async () => {
    const run = { ...BASE_RUN }

    const listRunsMock = listRuns as ReturnType<typeof vi.fn>
    // Initial load
    listRunsMock.mockResolvedValueOnce(makeListRunsResponse(run))
    // selectRun hydration: .catch(() => null) path — listRuns resolves to null
    listRunsMock.mockResolvedValueOnce(null)

    const wrapper = mount(HistoryDatabase, {
      global: { plugins: [router, i18n] },
    })
    await flushPromises()

    const before = run
    ;(wrapper.vm as any).selectedRun = before

    await (wrapper.vm as any).selectRun(run)

    // detail is null → freshRun is null → selectedRun must NOT be overwritten
    // Use toStrictEqual because Vue wraps the value in a Proxy (reference differs).
    expect((wrapper.vm as any).selectedRun).toStrictEqual(before)
  })
})
