/**
 * RunUsageBreakdown — Unit-Tests (Issue #764).
 *
 * Deckt ab: Gesamtwerte mit Status-Badges, Sortierung der Stage-Tabelle
 * (total_tokens desc) mit Top-Verbraucher-Markierung, Unknown-Kennzeichnung
 * (measurement_status, null-Werte als "—"), Warnungen + Abbruchgrund,
 * optionale Schätzung-vs.-Ist-Tabelle.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import RunUsageBreakdown from '../RunUsageBreakdown.vue'
import type {
  PreflightEstimate,
  RunBudgetStatus,
  RunUsage,
  UsageMetrics,
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

function makeMetrics(overrides: Partial<UsageMetrics> = {}): UsageMetrics {
  return {
    input_tokens: 30_000,
    output_tokens: 10_000,
    total_tokens: 40_000,
    llm_calls: 12,
    cost_micros: 500_000,
    cost_status: 'measured',
    tokens_status: 'measured',
    duration_ms: 60_000,
    ...overrides,
  }
}

function makeUsage(overrides: Partial<RunUsage> = {}): RunUsage {
  return {
    schema_version: 1,
    totals: makeMetrics(),
    by_stage: {
      simulation_rounds: makeMetrics({ total_tokens: 30_000, llm_calls: 10 }),
      graph_build: makeMetrics({ total_tokens: 10_000, llm_calls: 2 }),
    },
    by_provider: {
      openai: makeMetrics({ total_tokens: 40_000 }),
    },
    by_model: {
      'gpt-4o-mini': makeMetrics({ total_tokens: 40_000 }),
    },
    started_at: '2026-07-29T10:00:00Z',
    ended_at: '2026-07-29T10:05:00Z',
    measurement_status: 'complete',
    pricing_version: '2026-07',
    pricing_source: 'static',
    ...overrides,
  }
}

function makeBudget(overrides: Partial<RunBudgetStatus> = {}): RunBudgetStatus {
  return {
    config: {
      schema_version: 1,
      max_cost_micros: 1_000_000,
      enforcement: 'hard',
      currency: 'USD',
    },
    consumed: makeMetrics(),
    warnings: [],
    status: 'ok',
    ...overrides,
  }
}

function makeEstimate(): PreflightEstimate {
  return {
    schema_version: 1,
    is_estimate: true,
    estimated_tokens_low: 20_000,
    estimated_tokens_high: 60_000,
    estimated_cost_micros_low: 400_000,
    estimated_cost_micros_high: 800_000,
    estimated_duration_seconds_low: 60,
    estimated_duration_seconds_high: 180,
    cost_status: 'estimated',
    models: [],
    pricing_version: '2026-07',
    pricing_source: 'static',
    data_quality: 'medium',
    warnings: [],
  }
}

function mountBreakdown(props: {
  usage: RunUsage
  budget?: RunBudgetStatus | null
  estimate?: PreflightEstimate | null
}) {
  return mount(RunUsageBreakdown, {
    props,
    global: { plugins: [i18n] },
  })
}

describe('RunUsageBreakdown', () => {
  it('Gesamtwerte: Tokens/Kosten/Laufzeit/Aufrufe mit Status-Badges', () => {
    const wrapper = mountBreakdown({ usage: makeUsage() })
    expect(wrapper.find('[data-testid="usage-total-tokens"]').text()).toContain('40k')
    expect(nbsp(wrapper.find('[data-testid="usage-cost"]').text())).toContain('0,50 $')
    expect(wrapper.find('[data-testid="usage-duration"]').text()).toContain('1 min')
    expect(wrapper.find('[data-testid="usage-calls"]').text()).toContain('12')
    // Status-Badges an Tokens und Kosten.
    expect(wrapper.find('[data-testid="usage-total-tokens"] .v4-badge').exists()).toBe(true)
    expect(wrapper.find('[data-testid="usage-cost"] .v4-badge').exists()).toBe(true)
  })

  it('unbekannte Werte rendern als "—" (niemals 0), inkl. Badge', () => {
    const usage = makeUsage()
    usage.totals = makeMetrics({
      total_tokens: null,
      input_tokens: null,
      output_tokens: null,
      cost_micros: null,
      cost_status: 'unknown',
      tokens_status: 'unknown',
    })
    const wrapper = mountBreakdown({ usage })
    expect(wrapper.find('[data-testid="usage-total-tokens"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="usage-cost"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="usage-cost"]').text()).not.toContain('0,00')
  })

  it('measurement_status=partial wird sichtbar gekennzeichnet', () => {
    const wrapper = mountBreakdown({
      usage: makeUsage({ measurement_status: 'partial' }),
    })
    expect(wrapper.find('[data-testid="measurement-badge"]').exists()).toBe(true)
  })

  it('measurement_status=complete ohne Kennzeichnung', () => {
    const wrapper = mountBreakdown({ usage: makeUsage() })
    expect(wrapper.find('[data-testid="measurement-badge"]').exists()).toBe(false)
  })

  it('Stage-Tabelle: nach total_tokens desc sortiert, Top-Verbraucher markiert', () => {
    const usage = makeUsage({
      by_stage: {
        graph_build: makeMetrics({ total_tokens: 10_000, llm_calls: 2 }),
        simulation_rounds: makeMetrics({ total_tokens: 30_000, llm_calls: 10 }),
      },
    })
    const wrapper = mountBreakdown({ usage })
    const rows = wrapper.findAll('[data-testid="usage-by-stage"] tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('simulation_rounds')
    expect(rows[1].text()).toContain('graph_build')
    // Genau eine Top-Markierung, auf der ersten Zeile.
    expect(rows[0].classes()).toContain('rb-breakdown__row--top')
    expect(rows[1].classes()).not.toContain('rb-breakdown__row--top')
  })

  it('Provider- und Modell-Tabellen werden gerendert', () => {
    const wrapper = mountBreakdown({ usage: makeUsage() })
    expect(wrapper.find('[data-testid="usage-by-provider"]').text()).toContain('openai')
    expect(wrapper.find('[data-testid="usage-by-model"]').text()).toContain('gpt-4o-mini')
  })

  it('leere Breakdown-Records → keine Tabellen', () => {
    const wrapper = mountBreakdown({
      usage: makeUsage({ by_stage: {}, by_provider: {}, by_model: {} }),
    })
    expect(wrapper.find('[data-testid="usage-by-stage"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="usage-by-provider"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="usage-by-model"]').exists()).toBe(false)
  })

  it('Budget-Warnungen werden gelistet', () => {
    const budget = makeBudget({
      warnings: [
        {
          dimension: 'cost',
          severity: 'soft',
          threshold: 800_000,
          observed: 900_000,
          message: 'Kosten-Warnschwelle erreicht',
          ts: '2026-07-29T10:02:00Z',
        },
      ],
    })
    const wrapper = mountBreakdown({ usage: makeUsage(), budget })
    const warnings = wrapper.findAll('[data-testid="budget-warning"]')
    expect(warnings).toHaveLength(1)
    expect(warnings[0].text()).toContain('Kosten-Warnschwelle erreicht')
  })

  it('überschrittenes Budget zeigt Abbruchgrund-Banner', () => {
    const budget = makeBudget({ status: 'exceeded', exceeded_dimension: 'cost' })
    const wrapper = mountBreakdown({ usage: makeUsage(), budget })
    expect(wrapper.find('[data-testid="budget-exceeded-banner"]').exists()).toBe(true)
  })

  it('Budget ok → kein Abbruch-Banner', () => {
    const wrapper = mountBreakdown({ usage: makeUsage(), budget: makeBudget() })
    expect(wrapper.find('[data-testid="budget-exceeded-banner"]').exists()).toBe(false)
  })

  it('Schätzung vs. Ist nur, wenn estimate übergeben wird', () => {
    const withEstimate = mountBreakdown({ usage: makeUsage(), estimate: makeEstimate() })
    expect(withEstimate.find('[data-testid="estimate-vs-actual"]').exists()).toBe(true)
    const rows = withEstimate.findAll('[data-testid="estimate-vs-actual"] tbody tr')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('20k – 60k')
    expect(rows[0].text()).toContain('40k')

    const without = mountBreakdown({ usage: makeUsage() })
    expect(without.find('[data-testid="estimate-vs-actual"]').exists()).toBe(false)
  })
})
