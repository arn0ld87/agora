/**
 * Step2EnvSetup — refreshQuality-Tick-Isolation Tests (Sub-Slice J.1, Issue #219).
 *
 * Prueft: 5 Profile-Polls → genau 1 refreshQuality-Call (vorher: 5).
 * Der watch auf profiles.value.length darf refreshQuality nur beim
 * Übergang 0 → n>0 feuern, nicht bei jedem weiteren Tick.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

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

// Capture polling task functions as they are registered.
// usePolling is called 3× in order: pollPrepareStatus (0), fetchProfilesRealtime (1), fetchConfigRealtime (2).
const _capturedPollingTasks: Array<() => Promise<void>> = []

vi.mock('../../composables/usePolling', () => ({
  usePolling: vi.fn((task: () => Promise<void>) => {
    _capturedPollingTasks.push(task)
    return {
      isRunning: { value: false },
      isTicking: { value: false },
      tick: task,
      start: vi.fn(),
      stop: vi.fn(),
    }
  }),
}))

// --- Mutable mock state so individual tests can control API responses ---
let _profilesResponse: unknown = { success: true, data: { profiles: [] } }

vi.mock('../../api/simulation', () => ({
  prepareSimulation: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getPrepareStatus: vi.fn().mockResolvedValue({ success: true, data: { status: 'idle' } }),
  getSimulationProfilesRealtime: vi.fn().mockImplementation(() =>
    Promise.resolve(_profilesResponse),
  ),
  getSimulationConfigRealtime: vi.fn().mockResolvedValue({ success: false }),
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: { ollama: [], presets: [], current_default: '' },
  }),
  addSimulationProfile: vi.fn().mockResolvedValue({ success: true }),
  deleteSimulationProfile: vi.fn().mockResolvedValue({ success: true }),
  listPersonaTemplates: vi.fn().mockResolvedValue({ success: true, data: { templates: [] } }),
  savePersonaTemplate: vi.fn().mockResolvedValue({ success: true }),
  deletePersonaTemplate: vi.fn().mockResolvedValue({ success: true }),
}))

// refreshQuality-Spy.
const refreshQualitySpy = vi.fn().mockResolvedValue(undefined)

vi.mock('../../composables/usePersonaReview', () => ({
  usePersonaReview: vi.fn(() => ({
    refreshQuality: refreshQualitySpy,
    reviewEnabled: { value: false },
    error: { value: null },
    getIssuesFor: vi.fn().mockReturnValue([]),
    highestSeverityFor: vi.fn().mockReturnValue(null),
    approve: vi.fn().mockResolvedValue({ success: true }),
    reject: vi.fn().mockResolvedValue({ success: true }),
    editProfile: vi.fn().mockResolvedValue({ success: true }),
  })),
}))

vi.mock('../../composables/useSystemLog', () => ({
  useSystemLog: vi.fn(() => ({ addLog: vi.fn(), logs: { value: [] } })),
}))

import Step2EnvSetup from '../Step2EnvSetup.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

const globalConfig = {
  plugins: [i18n],
  stubs: {
    Btn: { template: '<button><slot /></button>' },
    Badge: { template: '<span><slot /></span>' },
    Kicker: { template: '<span><slot /></span>' },
    Field: { template: '<div><slot /></div>' },
    Select: { template: '<select><slot /></select>' },
  },
}

describe('Step2EnvSetup — refreshQuality-Tick-Isolation (J.1, #219)', () => {
  beforeEach(() => {
    refreshQualitySpy.mockClear()
    _capturedPollingTasks.length = 0
    _profilesResponse = { success: true, data: { profiles: [] } }
  })

  it('ruft refreshQuality bei 5 Polling-Ticks genau 1× auf (nur beim 0→n>0-Übergang)', async () => {
    mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-test-001',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    // usePolling ist 3× aufgerufen worden:
    // Index 0: pollPrepareStatus, Index 1: fetchProfilesRealtime, Index 2: fetchConfigRealtime
    expect(_capturedPollingTasks.length).toBeGreaterThanOrEqual(2)
    const fetchProfilesTask = _capturedPollingTasks[1]
    expect(typeof fetchProfilesTask).toBe('function')

    // Tick 1: profiles arrive (0 → 3) — watch should call refreshQuality 1×.
    _profilesResponse = {
      success: true,
      data: { profiles: [{ username: 'a' }, { username: 'b' }, { username: 'c' }] },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)

    // Ticks 2–5: same profiles count (3 → 3), no 0→n transition — no additional calls.
    for (let i = 0; i < 4; i++) {
      await fetchProfilesTask()
      await flushPromises()
      await nextTick()
    }

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)
    expect(refreshQualitySpy).toHaveBeenCalledWith('sim-test-001')
  })

  it('ruft refreshQuality bei Sim-Wechsel wieder 1× auf — neue Sim startet direkt mit Profilen (kein leerer Zwischen-Tick)', async () => {
    // Real scenario: sim-second already has profiles when simulationId prop changes.
    // The 1-watch variant must detect simId change (not profile 0→n transition)
    // and fire refreshQuality(simIdB) exactly once.
    const wrapper = mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-first',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    const fetchProfilesTask = _capturedPollingTasks[1]
    expect(typeof fetchProfilesTask).toBe('function')

    // Sim A: 3 profiles arrive → refreshQuality for sim-first.
    _profilesResponse = {
      success: true,
      data: { profiles: [{ username: 'a' }, { username: 'b' }, { username: 'c' }] },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)
    expect(refreshQualitySpy).toHaveBeenNthCalledWith(1, 'sim-first')

    // Sim-Wechsel: simulationId changes, sim-second already returns 5 profiles immediately.
    // No empty-profiles intermediate tick — this is the realistic production path.
    _profilesResponse = {
      success: true,
      data: {
        profiles: [
          { username: 'u' }, { username: 'v' }, { username: 'w' },
          { username: 'x' }, { username: 'y' },
        ],
      },
    }
    await wrapper.setProps({ simulationId: 'sim-second' })
    await flushPromises()
    await nextTick()

    // First poll for sim-second (with profiles already present) must trigger refreshQuality.
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    // Total: 1× for sim-first + 1× for sim-second = 2.
    expect(refreshQualitySpy).toHaveBeenCalledTimes(2)
    expect(refreshQualitySpy).toHaveBeenNthCalledWith(2, 'sim-second')

    wrapper.unmount()
  })

  it('feuert refreshQuality NICHT erneut wenn Profile-Anzahl innerhalb derselben Sim wächst (Guard hält)', async () => {
    // Guard must suppress re-triggers when profiles grow (e.g. 3 → 5 → 7) within the same sim.
    mount(Step2EnvSetup, {
      props: {
        simulationId: 'sim-stable',
        projectData: undefined,
        graphData: undefined,
        systemLogs: [],
      },
      global: globalConfig,
    })

    await flushPromises()

    const fetchProfilesTask = _capturedPollingTasks[1]
    expect(typeof fetchProfilesTask).toBe('function')

    // First poll: 3 profiles — must trigger refreshQuality once.
    _profilesResponse = {
      success: true,
      data: { profiles: [{ username: 'a' }, { username: 'b' }, { username: 'c' }] },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)

    // Subsequent polls: profile count grows (5, then 7) — guard must block re-triggers.
    _profilesResponse = {
      success: true,
      data: {
        profiles: [
          { username: 'a' }, { username: 'b' }, { username: 'c' },
          { username: 'd' }, { username: 'e' },
        ],
      },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    _profilesResponse = {
      success: true,
      data: {
        profiles: [
          { username: 'a' }, { username: 'b' }, { username: 'c' },
          { username: 'd' }, { username: 'e' }, { username: 'f' }, { username: 'g' },
        ],
      },
    }
    await fetchProfilesTask()
    await flushPromises()
    await nextTick()

    // Still exactly 1 call — guard held.
    expect(refreshQualitySpy).toHaveBeenCalledTimes(1)
    expect(refreshQualitySpy).toHaveBeenCalledWith('sim-stable')
  })
})
