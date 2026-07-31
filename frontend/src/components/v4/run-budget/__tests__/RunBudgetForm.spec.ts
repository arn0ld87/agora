/**
 * RunBudgetForm — Unit-Tests (Issue #764).
 *
 * Deckt ab: Leer→null, USD→Micros (Komma/Punkt), Minuten→Sekunden,
 * soft/hard-Umschalten, ungültige Werte (Fehler am Feld, kein neues Emit).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import RunBudgetForm from '../RunBudgetForm.vue'
import type { RunBudgetConfig } from '../../../../contracts/runBudgetContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

function mountForm(modelValue: RunBudgetConfig | null = null) {
  return mount(RunBudgetForm, {
    props: { modelValue },
    global: { plugins: [i18n] },
  })
}

/** Reihenfolge im Template: tokens, cost, duration, calls. */
function fields(wrapper: VueWrapper) {
  const inputs = wrapper.findAll('input')
  return {
    tokens: inputs[0],
    cost: inputs[1],
    duration: inputs[2],
    calls: inputs[3],
  }
}

function lastEmitted(wrapper: VueWrapper): RunBudgetConfig | null {
  const events = wrapper.emitted('update:modelValue')
  if (!events || events.length === 0) throw new Error('kein Emit vorhanden')
  return events.at(-1)![0] as RunBudgetConfig | null
}

describe('RunBudgetForm', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'de'
  })

  it('initial leer: kein Emit, alle Felder leer', () => {
    const wrapper = mountForm(null)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    for (const input of wrapper.findAll('input')) {
      expect((input.element as HTMLInputElement).value).toBe('')
    }
  })

  it('Leer → null: nach Tippen und Löschen wird null emittiert', async () => {
    const wrapper = mountForm(null)
    const { tokens } = fields(wrapper)
    await tokens.setValue('5000')
    expect(lastEmitted(wrapper)).toEqual({
      schema_version: 1,
      enforcement: 'soft',
      currency: 'USD',
      max_tokens: 5000,
    })
    await tokens.setValue('')
    expect(lastEmitted(wrapper)).toBeNull()
  })

  it('USD → Micros: "1,50" und "1.50" werden zu 1_500_000', async () => {
    const wrapper = mountForm(null)
    const { cost } = fields(wrapper)
    await cost.setValue('1,50')
    expect(lastEmitted(wrapper)?.max_cost_micros).toBe(1_500_000)
    await cost.setValue('1.50')
    expect(lastEmitted(wrapper)?.max_cost_micros).toBe(1_500_000)
    await cost.setValue('2')
    expect(lastEmitted(wrapper)?.max_cost_micros).toBe(2_000_000)
  })

  it('Minuten → Sekunden: "30" wird zu 1800', async () => {
    const wrapper = mountForm(null)
    const { duration } = fields(wrapper)
    await duration.setValue('30')
    expect(lastEmitted(wrapper)?.max_duration_seconds).toBe(1800)
  })

  it('LLM-Aufruf-Limit wird als Ganzzahl durchgereicht', async () => {
    const wrapper = mountForm(null)
    const { calls } = fields(wrapper)
    await calls.setValue('200')
    expect(lastEmitted(wrapper)?.max_llm_calls).toBe(200)
  })

  it('mehrere Limits gleichzeitig landen in einer Config', async () => {
    const wrapper = mountForm(null)
    const { tokens, cost, duration, calls } = fields(wrapper)
    await tokens.setValue('100000')
    await cost.setValue('0,75')
    await duration.setValue('10')
    await calls.setValue('50')
    expect(lastEmitted(wrapper)).toEqual({
      schema_version: 1,
      enforcement: 'soft',
      currency: 'USD',
      max_tokens: 100000,
      max_cost_micros: 750_000,
      max_duration_seconds: 600,
      max_llm_calls: 50,
    })
  })

  it('soft/hard-Umschalten emittiert dieselbe Config mit geändertem enforcement', async () => {
    const wrapper = mountForm(null)
    const { tokens } = fields(wrapper)
    await tokens.setValue('5000')
    expect(lastEmitted(wrapper)?.enforcement).toBe('soft')

    const segments = wrapper.findAll('.v4-segmented__seg')
    expect(segments).toHaveLength(2)
    await segments[1].trigger('click')
    expect(lastEmitted(wrapper)).toEqual({
      schema_version: 1,
      enforcement: 'hard',
      currency: 'USD',
      max_tokens: 5000,
    })

    await segments[0].trigger('click')
    expect(lastEmitted(wrapper)?.enforcement).toBe('soft')
  })

  it('ungültige Token-Eingabe: Fehler am Feld, aria-invalid, kein neues Emit', async () => {
    const wrapper = mountForm(null)
    const { tokens } = fields(wrapper)
    await tokens.setValue('5000')
    const emitCount = wrapper.emitted('update:modelValue')!.length

    await tokens.setValue('abc')
    expect(wrapper.emitted('update:modelValue')).toHaveLength(emitCount)
    expect(tokens.attributes('aria-invalid')).toBe('true')
    expect(wrapper.find('#rb-tokens-error').exists()).toBe(true)
    expect(wrapper.find('#rb-tokens-error').attributes('role')).toBe('alert')

    // Zurück zu valide: Fehler verschwindet, Emit geht wieder.
    await tokens.setValue('6000')
    expect(tokens.attributes('aria-invalid')).toBeUndefined()
    expect(lastEmitted(wrapper)?.max_tokens).toBe(6000)
  })

  it('0 ist kein gültiges Limit (nur positive Ganzzahlen)', async () => {
    const wrapper = mountForm(null)
    const { tokens } = fields(wrapper)
    await tokens.setValue('0')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(tokens.attributes('aria-invalid')).toBe('true')
  })

  it('ungültiger Kostenbetrag markiert das Kosten-Feld', async () => {
    const wrapper = mountForm(null)
    const { cost } = fields(wrapper)
    await cost.setValue('1,234')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(cost.attributes('aria-invalid')).toBe('true')
    expect(wrapper.find('#rb-cost-error').exists()).toBe(true)
  })

  it('spiegelt externes modelValue in die Felder (Micros → "1,50")', async () => {
    const wrapper = mountForm({
      schema_version: 1,
      enforcement: 'hard',
      currency: 'USD',
      max_tokens: 1000,
      max_cost_micros: 1_500_000,
      max_duration_seconds: 1800,
      max_llm_calls: 42,
    })
    const { tokens, cost, duration, calls } = fields(wrapper)
    expect((tokens.element as HTMLInputElement).value).toBe('1000')
    expect((cost.element as HTMLInputElement).value).toBe('1,50')
    expect((duration.element as HTMLInputElement).value).toBe('30')
    expect((calls.element as HTMLInputElement).value).toBe('42')

    await wrapper.setProps({ modelValue: null })
    for (const input of wrapper.findAll('input')) {
      expect((input.element as HTMLInputElement).value).toBe('')
    }
  })
})
