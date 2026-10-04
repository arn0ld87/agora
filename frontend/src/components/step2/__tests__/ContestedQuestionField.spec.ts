/**
 * ContestedQuestionField — Eingabe der Streitfrage vor der Vorbereitung
 * (Issue #1778, Schritt 1.6). Prüft: Label und Hilfetext, Längengrenze,
 * Weitergabe der Eingabe per `update:modelValue`, Sperre während der
 * Vorbereitung.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ContestedQuestionField from '../ContestedQuestionField.vue'
import de from '@/i18n/locales/de.json'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de, en: {} },
})

function mountComponent(props = {}) {
  return mount(ContestedQuestionField, {
    props: { modelValue: '', ...props },
    global: { plugins: [i18n] },
  })
}

describe('ContestedQuestionField (Issue #1778)', () => {
  it('rendert Label und Hilfetext', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('label').text()).toContain('Streitfrage (optional)')
    expect(wrapper.text()).toContain(
      'Eine Aussage, die man bejahen oder verneinen kann. Leer lassen, dann schlägt der Assistent eine vor.',
    )
  })

  it('verknüpft Label und Textfeld und begrenzt die Länge auf 300 Zeichen', () => {
    const wrapper = mountComponent()
    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('maxlength')).toBe('300')
    expect(wrapper.find('label').attributes('for')).toBe(textarea.attributes('id'))
  })

  it('zeigt den übergebenen Wert', () => {
    const wrapper = mountComponent({ modelValue: 'Die Kita am Berg wird geschlossen.' })
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toBe(
      'Die Kita am Berg wird geschlossen.',
    )
  })

  it('gibt die Eingabe per update:modelValue weiter', async () => {
    const wrapper = mountComponent()
    await wrapper.find('textarea').setValue('Die Kita am Berg wird geschlossen.')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([
      'Die Kita am Berg wird geschlossen.',
    ])
  })

  it('sperrt das Textfeld während der Vorbereitung', () => {
    const wrapper = mountComponent({ isPreparing: true })
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  })
})
