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
})
