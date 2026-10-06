import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

const api = vi.hoisted(() => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
  openSettingsStream: vi.fn(),
}))
vi.mock('@/api/settings', () => api)
vi.mock('../../../../api/settings', () => api)

import SectionBudgets from '../../sections/SectionBudgets.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

type Values = Record<string, number | string>

const SPECS = [
  ['AGORA_SIM_DEFAULT_MAX_TOKENS', 'int'],
  ['AGORA_SIM_DEFAULT_MAX_COST_MICROS', 'int'],
  ['AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS', 'int'],
  ['AGORA_SIM_DEFAULT_MAX_LLM_CALLS', 'int'],
  ['AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT', 'enum'],
] as const

function valuesEnvelope(values: Values) {
  return {
    success: true,
    data: {
      sections: ['budget'],
      fields: {
        budget: SPECS.map(([key, type]) => ({
          key,
          section: 'budget',
          type,
          secret: false,
          reload_required: false,
          source: 'default',
          is_set: true,
          value: values[key],
          default: values[key],
          ...(type === 'enum' ? { enum_values: ['soft', 'hard'] } : {}),
        })),
      },
    },
  }
}

function schemaEnvelope() {
  return {
    success: true,
    data: {
      sections: ['budget'],
      fields: SPECS.map(([key, type]) => ({
        key,
        section: 'budget',
        type,
        secret: false,
        reload_required: false,
        ...(type === 'enum' ? { enum_values: ['soft', 'hard'] } : {}),
      })),
    },
  }
}

const BASE: Values = {
  AGORA_SIM_DEFAULT_MAX_TOKENS: 20_000_000,
  AGORA_SIM_DEFAULT_MAX_COST_MICROS: 12_500_000,
  AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS: 7200,
  AGORA_SIM_DEFAULT_MAX_LLM_CALLS: 0,
  AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT: 'hard',
}

async function mountSection() {
  const wrapper = mount(SectionBudgets, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  api.fetchSettings.mockResolvedValue(valuesEnvelope(BASE))
  api.fetchSettingsSchema.mockResolvedValue(schemaEnvelope())
  api.openSettingsStream.mockResolvedValue({ close: vi.fn() })
})

describe('SectionBudgets', () => {
  it('zeigt Werte in USD und Stunden und den Hinweis zum Startdialog', async () => {
    const w = await mountSection()
    expect((w.get('#budget-tokens').element as HTMLInputElement).value).toBe('20000000')
    expect((w.get('#budget-cost').element as HTMLInputElement).value).toBe('12.5')
    expect((w.get('#budget-duration').element as HTMLInputElement).value).toBe('2')
    expect((w.get('select[aria-label="Einheit"]').element as HTMLSelectElement).value).toBe('hours')
    expect((w.get('#budget-enforcement').element as HTMLSelectElement).value).toBe('hard')
    expect(w.text()).toContain('ersetzt die Standardgrenzen vollständig')
    expect(w.text()).toContain('0 = kein Limit')
    expect(w.text()).not.toContain('In Vorbereitung')
    expect(w.find('h1').exists()).toBe(false)
  })

  it('speichert Kosten in Mikro-USD und Zeit in Sekunden, nur geänderte Felder', async () => {
    api.putSettings.mockResolvedValue(
      valuesEnvelope({
        ...BASE,
        AGORA_SIM_DEFAULT_MAX_COST_MICROS: 3_250_000,
        AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS: 5400,
        AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT: 'soft',
      }),
    )
    const w = await mountSection()
    await w.get('#budget-cost').setValue('3,25')
    await w.get('#budget-duration').setValue('90')
    await w.get('select[aria-label="Einheit"]').setValue('minutes')
    await w.get('#budget-enforcement').setValue('soft')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(api.putSettings).toHaveBeenCalledTimes(1)
    expect(api.putSettings).toHaveBeenCalledWith({
      AGORA_SIM_DEFAULT_MAX_COST_MICROS: 3_250_000,
      AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS: 5400,
      AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT: 'soft',
    })
    expect(w.text()).toContain('Gespeichert.')
    expect((w.get('#budget-cost').element as HTMLInputElement).value).toBe('3.25')
  })

  it('lehnt ungültige Eingaben ab, ohne die API aufzurufen', async () => {
    const w = await mountSection()
    await w.get('#budget-tokens').setValue('1.5')
    await w.get('#budget-cost').setValue('abc')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(api.putSettings).not.toHaveBeenCalled()
    expect(w.get('#budget-tokens-err').text()).toContain('ganze Zahl')
    expect(w.get('#budget-cost-err').text()).toContain('Zahl')
    expect(w.get('#budget-tokens').attributes('aria-invalid')).toBe('true')
  })

  it('zeigt Validierungsfehler der API am Feld und die Gesamtmeldung', async () => {
    api.putSettings.mockRejectedValue(
      Object.assign(new Error('Validierung fehlgeschlagen'), {
        originalResponse: {
          errors: [
            { key: 'AGORA_SIM_DEFAULT_MAX_TOKENS', code: 'out_of_range', message: 'zu groß' },
          ],
        },
      }),
    )
    const w = await mountSection()
    await w.get('#budget-tokens').setValue('5')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(w.get('#budget-tokens-err').text()).toContain('zu groß')
    expect(w.text()).toContain('Speichern fehlgeschlagen: Validierung fehlgeschlagen')
  })

  it('zeigt einen Ladefehler sichtbar', async () => {
    api.fetchSettings.mockRejectedValue(new Error('Netzwerk weg'))
    const w = await mountSection()
    expect(w.get('[role="alert"]').text()).toContain('Netzwerk weg')
    expect(w.find('form').exists()).toBe(false)
  })

  it('Verwerfen setzt die Eingaben zurück', async () => {
    const w = await mountSection()
    await w.get('#budget-calls').setValue('99')
    const buttons = w.findAll('button')
    await buttons[1].trigger('click')
    expect((w.get('#budget-calls').element as HTMLInputElement).value).toBe('0')
  })
})
