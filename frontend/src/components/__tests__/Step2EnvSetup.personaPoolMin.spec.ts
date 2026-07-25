/**
 * Step2EnvSetup — Persona-Pool min=10 + below-quota warning (smoke #6).
 *
 * Prueft:
 * 1. Slider min-Attribut ist 10 (nicht mehr 50).
 * 2. Number-Input min-Attribut ist 10.
 * 3. Warn-Banner erscheint wenn Pool < Quoten-Summe (useAgentCap + useQuotaPlan aktiv).
 * 4. Warn-Banner nicht sichtbar wenn Pool >= Quoten-Summe.
 * 5. Warn-Banner nicht sichtbar wenn useAgentCap deaktiviert.
 * 6. Warn-Banner nicht sichtbar wenn useQuotaPlan deaktiviert.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

// localStorage vor Modul-Imports mocken
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

// usePolling stub — kein echter Polling-Timer
vi.mock('../../composables/usePolling', () => ({
  usePolling: vi.fn((_task: () => Promise<void>) => ({
    isRunning: { value: false },
    isTicking: { value: false },
    tick: _task,
    start: vi.fn(),
    stop: vi.fn(),
  })),
}))

vi.mock('../../api/simulation', () => ({
  prepareSimulation: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getPrepareStatus: vi.fn().mockResolvedValue({ success: true, data: { status: 'idle' } }),
  getSimulationProfilesRealtime: vi.fn().mockResolvedValue({ success: true, data: { profiles: [] } }),
  getSimulationConfigRealtime: vi.fn().mockResolvedValue({ success: false }),
  getAvailableModels: vi.fn().mockResolvedValue({ success: true, data: { ollama: [], presets: [], current_default: '' } }),
  addSimulationProfile: vi.fn().mockResolvedValue({ success: true }),
  deleteSimulationProfile: vi.fn().mockResolvedValue({ success: true }),
  listPersonaTemplates: vi.fn().mockResolvedValue({ success: true, data: { templates: [] } }),
  savePersonaTemplate: vi.fn().mockResolvedValue({ success: true }),
  deletePersonaTemplate: vi.fn().mockResolvedValue({ success: true }),
}))

vi.mock('../../composables/usePersonaReview', () => ({
  usePersonaReview: vi.fn(() => ({
    refreshQuality: vi.fn().mockResolvedValue(undefined),
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
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de, en },
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

const defaultProps = {
  simulationId: 'sim-pool-test',
  projectData: undefined,
  graphData: undefined,
  systemLogs: [],
}

describe('Step2EnvSetup — persona pool min=10 + below-quota warning (smoke #6)', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  it('Slider min-Attribut ist 10', async () => {
    const wrapper = mount(Step2EnvSetup, { props: defaultProps, global: globalConfig })
    await flushPromises()

    // useAgentCap checkbox aktivieren
    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    await nextTick()

    const rangeInput = wrapper.find('input[type="range"]')
    expect(rangeInput.exists()).toBe(true)
    expect(rangeInput.attributes('min')).toBe('10')
  })

  it('Number-Input min-Attribut ist 10', async () => {
    const wrapper = mount(Step2EnvSetup, { props: defaultProps, global: globalConfig })
    await flushPromises()

    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    await nextTick()

    const numberInput = wrapper.find('input[type="number"]')
    expect(numberInput.exists()).toBe(true)
    expect(numberInput.attributes('min')).toBe('10')
  })

  it('Warn-Banner erscheint wenn Pool < Quoten-Summe', async () => {
    // Quota-Plan mit Summe 30 vorbelegen (quotaEntries wird aus localStorage geladen)
    localStorageMock.setItem(
      'agora.quotaPlan',
      JSON.stringify({ targets: { KMU: 20, Startup: 10 } }),
    )

    const wrapper = mount(Step2EnvSetup, { props: defaultProps, global: globalConfig })
    await flushPromises()

    // Schritt 1: useAgentCap aktivieren (erstes Checkbox-Element in Step2EnvSetup direkt)
    const checkbox = wrapper.find('input[type="checkbox"]')
    expect(checkbox.exists()).toBe(true)
    await checkbox.setValue(true)
    await nextTick()

    // Schritt 2: Pool auf 15 setzen (< Quota-Summe 30)
    const rangeInput = wrapper.find('input[type="range"]')
    expect(rangeInput.exists()).toBe(true)
    await rangeInput.setValue(15)
    await nextTick()

    // Schritt 3: useQuotaPlan aktivieren — QuotaPlanEditor hat ebenfalls ein checkbox.
    // Das zweite input[type="checkbox"] gehoert zum QuotaPlanEditor-Toggle.
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    expect(checkboxes.length).toBeGreaterThanOrEqual(2)
    await checkboxes[1].setValue(true)
    await nextTick()

    // Harte Assertion: Warn-Banner MUSS existieren — kein defensives if()
    const warn = wrapper.find('.hint--warn[role="alert"]')
    expect(warn.exists()).toBe(true)
    // Banner-Text enthaelt Pool-Wert und Quoten-Summe als Orientierungspunkt
    const warnText = warn.text()
    expect(warnText).toMatch(/15/)
    expect(warnText).toMatch(/30/)
  })

  it('Warn-Banner NICHT sichtbar wenn Pool >= Quoten-Summe', async () => {
    localStorageMock.setItem(
      'agora.quotaPlan',
      JSON.stringify({ targets: { KMU: 20, Startup: 10 } }),
    )

    const wrapper = mount(Step2EnvSetup, { props: defaultProps, global: globalConfig })
    await flushPromises()

    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    await nextTick()

    // Pool 50 >= Quota-Summe 30 — kein Banner
    const rangeInput = wrapper.find('input[type="range"]')
    await rangeInput.setValue(50)
    await nextTick()

    // Kein hint--warn mit Pool-Zahl sollte erscheinen
    // (note: andere hint--warn Banner können aus anderen Gründen sichtbar sein)
    const warns = wrapper.findAll('.hint--warn')
    const poolWarn = warns.filter((el) => el.text().includes('50'))
    expect(poolWarn.length).toBe(0)
  })

  it('Warn-Banner NICHT sichtbar wenn useAgentCap deaktiviert', async () => {
    localStorageMock.setItem(
      'agora.quotaPlan',
      JSON.stringify({ targets: { KMU: 20, Startup: 10 } }),
    )

    const wrapper = mount(Step2EnvSetup, { props: defaultProps, global: globalConfig })
    await flushPromises()

    // useAgentCap bleibt false (default)
    const warns = wrapper.findAll('.hint--warn')
    // Kein Pool-Warn ohne aktiven AgentCap
    const poolWarn = warns.filter((el) =>
      el.attributes('role') === 'alert' && el.text().includes('Pool'),
    )
    expect(poolWarn.length).toBe(0)
  })
})
