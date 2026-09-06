import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Select from '../Select.vue'

const OPTIONS = [
  { value: 'de', label: 'Deutschland' },
  { value: 'at', label: 'Österreich' },
  { value: 'ch', label: 'Schweiz' },
]

describe('Select', () => {
  it('renders all options', () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS },
    })
    const opts = w.findAll('option')
    expect(opts).toHaveLength(3)
    expect(opts[0].text()).toBe('Deutschland')
  })

  it('emits update:modelValue on change', async () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS },
    })
    await w.find('select').setValue('at')
    expect(w.emitted('update:modelValue')?.[0]).toEqual(['at'])
  })

  it('renders inline chevron SVG', () => {
    const w = mount(Select, {
      props: { modelValue: '', options: OPTIONS },
    })
    expect(w.find('.v4-select-chevron svg').exists()).toBe(true)
  })

  it('renders placeholder option when placeholder set and no value', () => {
    const w = mount(Select, {
      props: { modelValue: '', options: OPTIONS, placeholder: 'Bitte wählen' },
    })
    expect(w.find('option[disabled]').text()).toBe('Bitte wählen')
  })

  it('disables select when disabled prop set', () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS, disabled: true },
    })
    expect(w.find('.v4-select-wrap').classes()).toContain('v4-select-wrap--disabled')
  })

  it('rendert Label im label-Typo-Stil, wenn label gesetzt ist', () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS, label: 'Land' },
    })
    const label = w.find('.v4-select-label')
    expect(label.exists()).toBe(true)
    expect(label.text()).toBe('Land')
  })

  it('rendert Pflichtfeld-Sternchen, wenn required gesetzt ist', () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS, label: 'Land', required: true },
    })
    expect(w.find('.v4-select-required').exists()).toBe(true)
  })

  it('Regression #838: select behält den accessible name über aria-label, wenn label gesetzt ist', () => {
    // axe-core select-name (critical): das sichtbare <label> ist nicht per
    // for/id mit dem <select> verknüpft — aria-label spiegelt den Labeltext,
    // damit Screenreader trotzdem einen Namen bekommen.
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS, label: 'Land' },
    })
    expect(w.find('select').attributes('aria-label')).toBe('Land')
  })

  it('ohne label bleibt aria-label unbesetzt', () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS },
    })
    expect(w.find('select').attributes('aria-label')).toBeUndefined()
    expect(w.find('.v4-select-label').exists()).toBe(false)
  })

  it('verknüpft das sichtbare Label über for/id mit dem select', () => {
    // Ein Klick auf das Label soll das Steuerelement fokussieren — dafür reicht
    // aria-label nicht, es braucht die for/id-Verknüpfung.
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS, label: 'Land' },
    })
    const selectId = w.find('select').attributes('id')

    expect(selectId).toBeTruthy()
    expect(w.find('label').attributes('for')).toBe(selectId)
  })

  it('required setzt die native Validierungs-Constraint am select', () => {
    // Der Sternchen-Marker allein verhindert kein Absenden ohne Auswahl.
    const w = mount(Select, {
      props: { modelValue: '', options: OPTIONS, label: 'Land', required: true, placeholder: 'Bitte wählen' },
    })
    expect((w.find('select').element as HTMLSelectElement).required).toBe(true)
  })

  it('ohne required bleibt das select ohne Validierungs-Constraint', () => {
    const w = mount(Select, {
      props: { modelValue: 'de', options: OPTIONS, label: 'Land' },
    })
    expect((w.find('select').element as HTMLSelectElement).required).toBe(false)
  })
})
