/**
 * ActivityModeField — Wahl des Aktivitätsmodus vor der Vorbereitung
 * (Issue #1779, Schritt 2.4). Prüft: Gruppenbeschriftung, Optionen mit
 * Hilfetext, Vorauswahl, Wechsel, Sperre während der Vorbereitung.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ActivityModeField from '../ActivityModeField.vue'
import de from '@/i18n/locales/de.json'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de, en: {} },
})

function mountComponent(props = {}) {
  return mount(ActivityModeField, {
    props: { modelValue: 'realistic', ...props },
    global: { plugins: [i18n] },
  })
}

describe('ActivityModeField (Issue #1779)', () => {
  it('rendert eine beschriftete Gruppe mit zwei Optionen und Hilfetexten', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('fieldset legend').text()).toBe('Aktivität der Agenten')
    const labels = wrapper.findAll('label')
    expect(labels).toHaveLength(2)
    expect(labels[0].text()).toContain('Realistisch')
    expect(labels[0].text()).toContain(
      'Belegte Durchschnittswerte: Die meisten Akteure schreiben etwa einmal am Tag oder seltener. Für viele Beiträge mehr Agenten oder mehr simulierte Tage wählen.',
    )
    expect(labels[1].text()).toContain('Aktiv')
    expect(labels[1].text()).toContain(
      'Oberes Ende der belegten Spannen: zwei bis drei Beiträge je Akteur und Tag.',
    )
  })

  it('wählt „Realistisch" vor und gruppiert die Radios unter einem Namen', () => {
    const wrapper = mountComponent()
    const radios = wrapper.findAll('input[type="radio"]')
    expect((radios[0].element as HTMLInputElement).checked).toBe(true)
    expect((radios[1].element as HTMLInputElement).checked).toBe(false)
    expect(radios[0].attributes('name')).toBe(radios[1].attributes('name'))
    expect(radios[0].attributes('aria-describedby')).toBeTruthy()
  })

  it('meldet den Wechsel auf „active" per update:modelValue', async () => {
    const wrapper = mountComponent()
    await wrapper.findAll('input[type="radio"]')[1].setValue(true)
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['active'])
  })

  it('zeigt eine übergebene Auswahl „active"', () => {
    const wrapper = mountComponent({ modelValue: 'active' })
    const radios = wrapper.findAll('input[type="radio"]')
    expect((radios[1].element as HTMLInputElement).checked).toBe(true)
  })

  it('sperrt die Gruppe während der Vorbereitung', () => {
    const wrapper = mountComponent({ isPreparing: true })
    expect(wrapper.find('fieldset').attributes('disabled')).toBeDefined()
  })
})
