/**
 * PreflightEstimateCard — Unit-Tests (Issue #764).
 *
 * Deckt ab: Bereichsformatierung (Tokens/Kosten/Laufzeit), Unknown-Zustände
 * (niemals 0), Modelle mit Status-Badges, Warnungen, Loading/Error/Empty.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import PreflightEstimateCard from '../PreflightEstimateCard.vue'
import type { PreflightEstimate } from '../../../../contracts/runBudgetContract'

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

function makeEstimate(overrides: Partial<PreflightEstimate> = {}): PreflightEstimate {
  return {
    schema_version: 1,
    is_estimate: true,
    estimated_tokens_low: 12_000,
    estimated_tokens_high: 40_000,
    estimated_cost_micros_low: 500_000,
    estimated_cost_micros_high: 1_500_000,
    estimated_duration_seconds_low: 300,
    estimated_duration_seconds_high: 900,
    cost_status: 'estimated',
    models: [
      {
        stage: 'simulation_rounds',
        provider_id: 'openai',
        model_id: 'gpt-4o-mini',
        cost_status: 'estimated',
      },
      {
        stage: 'report',
        provider_id: 'ollama',
        model_id: 'llama3.1',
        cost_status: 'free',
      },
    ],
    pricing_version: '2026-07',
    pricing_source: 'static',
    data_quality: 'medium',
    warnings: [],
    ...overrides,
  }
}

function mountCard(props: {
  estimate: PreflightEstimate | null
  loading?: boolean
  error?: string | null
}) {
  return mount(PreflightEstimateCard, {
    props,
    global: { plugins: [i18n] },
  })
}

describe('PreflightEstimateCard', () => {
  it('estimate=null ohne loading: Empty-Hinweis, kein Schätzungs-Badge', () => {
    const wrapper = mountCard({ estimate: null })
    expect(wrapper.find('.rb-preflight__empty').exists()).toBe(true)
    expect(wrapper.find('[data-testid="estimate-badge"]').exists()).toBe(false)
  })

  it('loading: Ladehinweis statt Empty-State', () => {
    const wrapper = mountCard({ estimate: null, loading: true })
    expect(wrapper.find('.rb-preflight__loading').exists()).toBe(true)
    expect(wrapper.find('.rb-preflight__empty').exists()).toBe(false)
  })

  it('error: Danger-Alert mit Fehlertext', () => {
    const wrapper = mountCard({ estimate: null, error: 'Provider nicht erreichbar' })
    const alert = wrapper.find('[data-testid="estimate-error"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('Provider nicht erreichbar')
  })

  it('Schätzung: Bereiche werden als Range formatiert', () => {
    const wrapper = mountCard({ estimate: makeEstimate() })
    expect(wrapper.find('[data-testid="estimate-badge"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="estimate-tokens"]').text()).toBe('12k – 40k')
    expect(nbsp(wrapper.find('[data-testid="estimate-cost"]').text())).toContain('0,50 $ – 1,50 $')
    expect(wrapper.find('[data-testid="estimate-duration"]').text()).toBe('5 min – 15 min')
    expect(wrapper.find('[data-testid="estimate-quality"]').exists()).toBe(true)
  })

  it('Unknown-Zustände rendern als "—", niemals als 0', () => {
    const wrapper = mountCard({
      estimate: makeEstimate({
        estimated_tokens_low: null,
        estimated_tokens_high: null,
        estimated_cost_micros_low: null,
        estimated_cost_micros_high: null,
        estimated_duration_seconds_low: null,
        estimated_duration_seconds_high: null,
        cost_status: 'unknown',
        data_quality: 'unknown',
      }),
    })
    expect(wrapper.find('[data-testid="estimate-tokens"]').text()).toBe('—')
    expect(wrapper.find('[data-testid="estimate-cost"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="estimate-cost"]').text()).not.toContain('0,00')
    expect(wrapper.find('[data-testid="estimate-duration"]').text()).toBe('—')
  })

  it('Modelle werden mit Provider/Modell und Status-Badge gelistet', () => {
    const wrapper = mountCard({ estimate: makeEstimate() })
    const models = wrapper.findAll('.rb-preflight__model')
    expect(models).toHaveLength(2)
    expect(models[0].text()).toContain('simulation_rounds')
    expect(models[0].text()).toContain('openai/gpt-4o-mini')
    expect(models[1].text()).toContain('ollama/llama3.1')
    // Jedes Modell trägt ein cost_status-Badge.
    for (const model of models) {
      expect(model.find('.v4-badge').exists()).toBe(true)
    }
  })

  it('Warnungen werden als Warning-Alert-Liste gerendert', () => {
    const wrapper = mountCard({
      estimate: makeEstimate({ warnings: ['Preisstand veraltet', 'Keine Preise für ollama'] }),
    })
    const warnings = wrapper.find('[data-testid="estimate-warnings"]')
    expect(warnings.exists()).toBe(true)
    const items = warnings.findAll('li')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toBe('Preisstand veraltet')
  })

  it('ohne Warnungen kein Warnungs-Alert', () => {
    const wrapper = mountCard({ estimate: makeEstimate({ warnings: [] }) })
    expect(wrapper.find('[data-testid="estimate-warnings"]').exists()).toBe(false)
  })

  it('gleiche low/high-Werte kollabieren zum Einzelwert', () => {
    const wrapper = mountCard({
      estimate: makeEstimate({
        estimated_tokens_low: 5000,
        estimated_tokens_high: 5000,
      }),
    })
    expect(wrapper.find('[data-testid="estimate-tokens"]').text()).toBe('5k')
  })
})
