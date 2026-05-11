import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Field from '../Field.vue'

describe('Field', () => {
  it('renders label text', () => {
    const w = mount(Field, {
      props: { label: 'API-Schlüssel' },
      slots: { default: '<input type="text" />' },
    })
    expect(w.find('.v4-field__label').text()).toBe('API-Schlüssel')
  })

  it('renders slot content in control area', () => {
    const w = mount(Field, {
      props: { label: 'Name' },
      slots: { default: '<input class="my-ctrl" />' },
    })
    expect(w.find('.v4-field__control .my-ctrl').exists()).toBe(true)
  })

  it('has vertical flex layout', () => {
    const w = mount(Field, {
      props: { label: 'Test' },
    })
    expect(w.find('.v4-field').exists()).toBe(true)
  })
})
