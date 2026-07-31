/**
 * RunResourceMonitor — Unit-Tests (Issue #764).
 *
 * Deckt ab: Fortschrittsbalken pro gesetzter Dimension (aria-Attribute),
 * Warnungen (soft/hard), Budgetabbruch-Banner (Prop oder gepollt),
 * No-Budget-Hinweis, Polling-Verhalten (Start bei aktivem Status, Stopp +
 * letzter Tick bei terminalem Status). getRun ist gemockt — kein Backend.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

vi.mock('../../../../api/runs', () => ({
  getRun: vi.fn(),
}))

import RunResourceMonitor from '../RunResourceMonitor.vue'
import { getRun } from '../../../../api/runs'
import type { RunRecord } from '../../../../types/run'
import type {
  RunBudgetStatus,
  TerminationReason,
} from '../../../../contracts/runBudgetContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

/** NBSP/narrow-NBSP → normales Leerzeichen (ICU-Drift). */
function nbsp(s: string): string {
  return s.replace(/[\u00a0\u202f]/g, ' ')
}

function makeBudget(overrides: Partial<RunBudgetStatus> = {}): RunBudgetStatus {
  return {
    config: {
      schema_version: 1,
      max_tokens: 100_000,
      max_cost_micros: 2_000_000,
      enforcement: 'hard',
      currency: 'USD',
    },
    consumed: {
      input_tokens: 30_000,
      output_tokens: 10_000,
      total_tokens: 40_000,
      llm_calls: 12,
      cost_micros: 500_000,
      cost_status: 'measured',
      tokens_status: 'measured',
      duration_ms: 60_000,
    },
    warnings: [],
    status: 'ok',
    ...overrides,
  }
}

function mockGetRun(data: Record<string, unknown>) {
  // Nur die Anreicherungs-Felder (budget/usage/termination_reason) sind für
  // den Monitor relevant — der Rest des RunRecord bleibt im Mock leer.
  vi.mocked(getRun).mockResolvedValue({
    success: true,
    data: data as unknown as RunRecord,
  })
}

function mountMonitor(props: {
  runId?: string
  status?: string
  terminationReason?: TerminationReason | null
} = {}) {
  return mount(RunResourceMonitor, {
    props: {
      runId: 'run_1',
      status: 'processing',
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('RunResourceMonitor', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(getRun).mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('rendert Fortschrittsbalken nur für gesetzte Dimensionen', async () => {
    mockGetRun({ budget: makeBudget(), usage: null, termination_reason: null })
    const wrapper = mountMonitor()
    await flushPromises()

    expect(wrapper.find('[data-testid="budget-row-tokens"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="budget-row-cost"]').exists()).toBe(true)
    // Zeit/Aufrufe sind in der Config nicht gesetzt → keine Balken.
    expect(wrapper.find('[data-testid="budget-row-time"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="budget-row-calls"]').exists()).toBe(false)

    const tokensRow = wrapper.find('[data-testid="budget-row-tokens"]')
    expect(tokensRow.text()).toContain('40k')
    expect(tokensRow.text()).toContain('100k')
    expect(tokensRow.text()).toContain('60k')
    const bar = tokensRow.find('[role="progressbar"]')
    expect(bar.attributes('aria-valuemin')).toBe('0')
    expect(bar.attributes('aria-valuemax')).toBe('100000')
    expect(bar.attributes('aria-valuenow')).toBe('40000')

    expect(nbsp(wrapper.find('[data-testid="budget-row-cost"]').text())).toContain('0,50 $')
  })

  it('unbekannter Verbrauch (null) → "—" und kein aria-valuenow', async () => {
    const budget = makeBudget()
    budget.consumed = { ...budget.consumed, total_tokens: null }
    mockGetRun({ budget, usage: null, termination_reason: null })
    const wrapper = mountMonitor()
    await flushPromises()

    const tokensRow = wrapper.find('[data-testid="budget-row-tokens"]')
    expect(tokensRow.text()).toContain('—')
    const bar = tokensRow.find('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBeUndefined()
    expect(bar.classes()).toContain('rb-monitor__bar--unknown')
  })

  it('Warnungen: soft → warning-Ton, hard → danger-Ton', async () => {
    const budget = makeBudget({
      status: 'warning',
      warnings: [
        {
          dimension: 'tokens',
          severity: 'soft',
          threshold: 80_000,
          observed: 81_000,
          message: 'Token-Warnschwelle erreicht',
          ts: '2026-07-29T10:00:00Z',
        },
        {
          dimension: 'cost',
          severity: 'hard',
          threshold: 2_000_000,
          observed: 2_100_000,
          message: 'Kosten-Limit überschritten',
          ts: '2026-07-29T10:01:00Z',
        },
      ],
    })
    mockGetRun({ budget, usage: null, termination_reason: null })
    const wrapper = mountMonitor()
    await flushPromises()

    const warnings = wrapper.findAll('[data-testid="budget-warning"]')
    expect(warnings).toHaveLength(2)
    expect(warnings[0].classes()).toContain('al-root--warning')
    expect(warnings[0].text()).toContain('Token-Warnschwelle erreicht')
    expect(warnings[1].classes()).toContain('al-root--danger')
  })

  it('Budgetabbruch-Banner via terminationReason-Prop', async () => {
    mockGetRun({ budget: makeBudget(), usage: null, termination_reason: null })
    const wrapper = mountMonitor({ terminationReason: 'budget_tokens' })
    await flushPromises()
    expect(wrapper.find('[data-testid="budget-stop-banner"]').exists()).toBe(true)
  })

  it('Budgetabbruch-Banner aus der gepollten Run-Antwort', async () => {
    mockGetRun({
      budget: makeBudget({ status: 'exceeded', exceeded_dimension: 'cost' }),
      usage: null,
      termination_reason: 'budget_cost',
    })
    const wrapper = mountMonitor()
    await flushPromises()
    expect(wrapper.find('[data-testid="budget-stop-banner"]').exists()).toBe(true)
  })

  it('kein Budget-Abbruch → kein Banner', async () => {
    mockGetRun({ budget: makeBudget(), usage: null, termination_reason: 'completed' })
    const wrapper = mountMonitor()
    await flushPromises()
    expect(wrapper.find('[data-testid="budget-stop-banner"]').exists()).toBe(false)
  })

  it('ohne Budget: Hinweis statt Balken', async () => {
    mockGetRun({ budget: null, usage: null, termination_reason: null })
    const wrapper = mountMonitor()
    await flushPromises()
    expect(wrapper.find('[data-testid="budget-none"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="budget-row-tokens"]').exists()).toBe(false)
  })

  it('pollt alle 5 s, solange der Status aktiv ist', async () => {
    mockGetRun({ budget: makeBudget(), usage: null, termination_reason: null })
    mountMonitor()
    await flushPromises()
    expect(getRun).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(5000)
    expect(getRun).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(getRun).toHaveBeenCalledTimes(4)
  })

  it('stoppt bei terminalem Status und fährt genau einen Abschluss-Tick', async () => {
    mockGetRun({ budget: makeBudget(), usage: null, termination_reason: null })
    const wrapper = mountMonitor()
    await flushPromises()
    expect(getRun).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ status: 'completed' })
    await flushPromises()
    // Ein finaler Tick für die Endwerte.
    expect(getRun).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(15_000)
    expect(getRun).toHaveBeenCalledTimes(2)
  })

  it('bei inaktivem Start-Status wird nicht gepollt', async () => {
    mockGetRun({ budget: makeBudget(), usage: null, termination_reason: null })
    mountMonitor({ status: 'completed' })
    await flushPromises()
    expect(getRun).not.toHaveBeenCalled()
  })
})
