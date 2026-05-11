import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Badge from '../Badge.vue'

describe('Badge', () => {
  it('renders slot text', () => {
    const w = mount(Badge, { slots: { default: 'Done' } })
    expect(w.text()).toContain('Done')
  })

  it('applies tone class', () => {
    const w = mount(Badge, { props: { tone: 'green' }, slots: { default: 'OK' } })
    expect(w.find('.v4-badge').classes()).toContain('v4-badge--green')
  })

  it('shows dot by default', () => {
    const w = mount(Badge, { slots: { default: 'X' } })
    expect(w.find('.v4-badge__dot').exists()).toBe(true)
  })

  it('hides dot when dot=false', () => {
    const w = mount(Badge, { props: { dot: false }, slots: { default: 'X' } })
    expect(w.find('.v4-badge__dot').exists()).toBe(false)
  })

  it('defaults to gray tone', () => {
    const w = mount(Badge, { slots: { default: 'Draft' } })
    expect(w.find('.v4-badge').classes()).toContain('v4-badge--gray')
  })

  it('renders all tones without error', () => {
    const tones = ['green', 'orange', 'red', 'purple', 'teal', 'blue', 'gray'] as const
    for (const tone of tones) {
      const w = mount(Badge, { props: { tone }, slots: { default: tone } })
      expect(w.find(`.v4-badge--${tone}`).exists()).toBe(true)
    }
  })
})
