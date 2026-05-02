import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ConfidenceBadge, { deriveLabel } from '../ConfidenceBadge.vue'

describe('deriveLabel', () => {
  it('derives label from score', () => {
    expect(deriveLabel(0.9)).toBe('verified')
    expect(deriveLabel(0.85)).toBe('verified')
    expect(deriveLabel(0.84)).toBe('high')
    expect(deriveLabel(0.75)).toBe('high')
    expect(deriveLabel(0.74)).toBe('medium')
    expect(deriveLabel(0.45)).toBe('medium')
    expect(deriveLabel(0.44)).toBe('low')
    expect(deriveLabel(0)).toBe('low')
  })
})

describe('ConfidenceBadge', () => {
  it('renders verified for score 0.9', () => {
    const w = mount(ConfidenceBadge, { props: { score: 0.9, auditTrail: [] } })
    expect(w.classes()).toContain('is-verified')
    expect(w.text()).toContain('90%')
  })

  it('renders medium for score 0.6', () => {
    const w = mount(ConfidenceBadge, { props: { score: 0.6, auditTrail: [] } })
    expect(w.classes()).toContain('is-medium')
  })

  it('renders low for score 0.1', () => {
    const w = mount(ConfidenceBadge, { props: { score: 0.1, auditTrail: [] } })
    expect(w.classes()).toContain('is-low')
  })

  it('shows audit popover on mouseenter', async () => {
    const w = mount(ConfidenceBadge, {
      props: {
        score: 0.7,
        auditTrail: [
          { source: 'agent_log', snippet: 'Trace A' },
          { source: 'web_tool', snippet: 'Suchquelle' },
        ],
      },
    })
    // Popover noch nicht sichtbar
    expect(w.find('.audit-popover').exists()).toBe(false)
    await w.trigger('mouseenter')
    const popover = w.find('.audit-popover')
    expect(popover.exists()).toBe(true)
    expect(popover.text()).toContain('Trace A')
    expect(popover.text()).toContain('Suchquelle')
  })

  it('hides popover when audit_trail empty (or shows leeres-state)', async () => {
    const w = mount(ConfidenceBadge, { props: { score: 0.7, auditTrail: [] } })
    await w.trigger('mouseenter')
    // Akzeptiere beide Strategien:
    const popover = w.find('.audit-popover')
    if (popover.exists()) {
      expect(popover.text()).toMatch(/Keine Audit/i)
    }
  })

  it('renders high for score 0.8 when label not given', () => {
    const w = mount(ConfidenceBadge, { props: { score: 0.8 } })
    expect(w.classes()).toContain('is-high')
  })

  it('respects explicit label prop (overrides score-derived)', () => {
    // score=0.9 wuerde 'verified' ergeben, aber label='low' explizit
    const w = mount(ConfidenceBadge, { props: { score: 0.9, label: 'low' } })
    expect(w.classes()).toContain('is-low')
  })

  it('hides percentage when showCount=false', () => {
    const w = mount(ConfidenceBadge, { props: { score: 0.9, showCount: false } })
    expect(w.text()).not.toContain('%')
    expect(w.text()).toContain('verified')
  })
})
