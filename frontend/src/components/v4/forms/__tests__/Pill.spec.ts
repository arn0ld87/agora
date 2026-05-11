import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import Pill from '../Pill.vue'

describe('Pill', () => {
  it('renders as Badge with correct tone', () => {
    const w = mount(Pill, { props: { tone: 'teal' }, slots: { default: 'Queued' } })
    // Pill wraps Badge — check the rendered badge class
    expect(w.find('.v4-badge--teal').exists()).toBe(true)
    expect(w.text()).toContain('Queued')
  })

  it('shows dot by default', () => {
    const w = mount(Pill, { slots: { default: 'Running' } })
    expect(w.find('.v4-badge__dot').exists()).toBe(true)
  })
})
