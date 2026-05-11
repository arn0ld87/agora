import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import SegmentedControl from '../SegmentedControl.vue'

const OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

describe('SegmentedControl', () => {
  it('renders all options as buttons', () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS },
    })
    const buttons = w.findAll('.v4-segmented__seg')
    expect(buttons).toHaveLength(3)
    expect(buttons[0].text()).toBe('Low')
  })

  it('marks active option with active class', () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'medium', options: OPTIONS },
    })
    const buttons = w.findAll('.v4-segmented__seg')
    expect(buttons[1].classes()).toContain('v4-segmented__seg--active')
    expect(buttons[0].classes()).not.toContain('v4-segmented__seg--active')
  })

  it('emits update:modelValue on click', async () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS },
    })
    await w.findAll('.v4-segmented__seg')[2].trigger('click')
    expect(w.emitted('update:modelValue')?.[0]).toEqual(['high'])
  })
})
