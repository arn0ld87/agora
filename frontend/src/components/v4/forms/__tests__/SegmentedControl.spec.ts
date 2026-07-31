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

describe('SegmentedControl — disabled', () => {
  it('Maus: Klick im Disabled-Zustand emittiert nicht', async () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS, disabled: true },
    })
    await w.findAll('.v4-segmented__seg')[2].trigger('click')
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('Enter/Space: Tastatur-Aktivierung im Disabled-Zustand emittiert nicht', async () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS, disabled: true },
    })
    const seg = w.findAll('.v4-segmented__seg')[1]
    await seg.trigger('keydown', { key: 'Enter' })
    await seg.trigger('keydown', { key: ' ' })
    await seg.trigger('keydown', { key: 'Spacebar' })
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('Fokus-Skip: jeden Button semantisch aus dem Tab-Ring nehmen', () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS, disabled: true },
    })
    for (const seg of w.findAll('.v4-segmented__seg')) {
      expect(seg.attributes('tabindex')).toBe('-1')
      expect(seg.attributes('disabled')).toBeDefined()
      expect(seg.attributes('aria-disabled')).toBe('true')
    }
    // Gruppe signalisiert den Disabled-Zustand zusätzlich.
    expect(w.find('.v4-segmented').attributes('aria-disabled')).toBe('true')
  })

  it('keine Emission: weder Maus noch Tastatur lösen update:modelValue aus', async () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS, disabled: true },
    })
    const segs = w.findAll('.v4-segmented__seg')
    await segs[0].trigger('click')
    await segs[2].trigger('keydown', { key: 'Enter' })
    await segs[1].trigger('click')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    // modelValue bleibt unverändert (kein internes Umschalten).
    expect(w.props('modelValue')).toBe('low')
  })

  it('Normalbetrieb: ohne disabled schaltet Klick normal durch', async () => {
    const w = mount(SegmentedControl, {
      props: { modelValue: 'low', options: OPTIONS, disabled: false },
    })
    const segs = w.findAll('.v4-segmented__seg')
    // Kein Disabled-Attribut, im Tab-Ring, keine aria-disabled.
    expect(segs[0].attributes('disabled')).toBeUndefined()
    expect(segs[0].attributes('aria-disabled')).toBeUndefined()
    expect(segs[0].attributes('tabindex')).not.toBe('-1')
    await segs[2].trigger('click')
    expect(w.emitted('update:modelValue')?.[0]).toEqual(['high'])
  })
})