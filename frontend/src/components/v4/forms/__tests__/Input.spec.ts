import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Input from '../Input.vue'

describe('Input', () => {
  it('renders with modelValue', () => {
    const w = mount(Input, { props: { modelValue: 'sk-abc', type: 'text' } })
    const el = w.find('.v4-input').element as HTMLInputElement
    expect(el.value).toBe('sk-abc')
  })

  it('emits update:modelValue on input', async () => {
    const w = mount(Input, { props: { modelValue: '', type: 'text' } })
    const input = w.find('.v4-input')
    await input.setValue('hallo')
    expect(w.emitted('update:modelValue')?.[0]).toEqual(['hallo'])
  })

  it('applies mono class when mono prop set', () => {
    const w = mount(Input, { props: { modelValue: '', mono: true } })
    expect(w.find('.v4-input').classes()).toContain('v4-input--mono')
  })

  it('is disabled when disabled prop set', () => {
    const w = mount(Input, { props: { modelValue: '', disabled: true } })
    const el = w.find('.v4-input').element as HTMLInputElement
    expect(el.disabled).toBe(true)
  })

  it('renders correct input type', () => {
    const w = mount(Input, { props: { modelValue: '', type: 'password' } })
    const el = w.find('.v4-input').element as HTMLInputElement
    expect(el.type).toBe('password')
  })

  it('renders placeholder', () => {
    const w = mount(Input, { props: { modelValue: '', placeholder: 'Suchbegriff' } })
    const el = w.find('.v4-input').element as HTMLInputElement
    expect(el.placeholder).toBe('Suchbegriff')
  })
})
