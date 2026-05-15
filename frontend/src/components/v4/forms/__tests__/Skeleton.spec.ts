/**
 * Skeleton — Tests
 * Slice UI-D · 2026-05-15
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Skeleton from '../Skeleton.vue'

describe('Skeleton', () => {
  it('Test 1: Default-Mount rendert Rect-Variant', () => {
    const wrapper = mount(Skeleton)

    const rect = wrapper.find('.sk--rect')
    expect(rect.exists()).toBe(true)
    expect(rect.attributes('role')).toBe('status')
    expect(rect.attributes('aria-busy')).toBe('true')
  })

  it('Test 2: variant=text mit lines=3 rendert drei Zeilen + Stack', () => {
    const wrapper = mount(Skeleton, {
      props: { variant: 'text', lines: 3 },
    })

    expect(wrapper.find('.sk-stack').exists()).toBe(true)
    const lines = wrapper.findAll('.sk--text')
    expect(lines).toHaveLength(3)
  })

  it('Test 3: variant=text mit lines>1 staucht letzte Zeile auf 70%', () => {
    const wrapper = mount(Skeleton, {
      props: { variant: 'text', lines: 2, width: '300px' },
    })

    const lines = wrapper.findAll('.sk--text')
    expect(lines[0].attributes('style')).toContain('width: 300px')
    expect(lines[1].attributes('style')).toContain('width: 70%')
  })

  it('Test 4: variant=text mit lines=1 nutzt volle Breite (kein 70%-Stauch)', () => {
    const wrapper = mount(Skeleton, {
      props: { variant: 'text', lines: 1, width: '200px' },
    })

    const line = wrapper.find('.sk--text')
    expect(line.attributes('style')).toContain('width: 200px')
  })

  it('Test 5: variant=circle nutzt size für width und height', () => {
    const wrapper = mount(Skeleton, {
      props: { variant: 'circle', size: '48px' },
    })

    const circle = wrapper.find('.sk--circle')
    expect(circle.exists()).toBe(true)
    expect(circle.attributes('style')).toContain('width: 48px')
    expect(circle.attributes('style')).toContain('height: 48px')
  })

  it('Test 6: Screen-Reader-Text vorhanden für a11y', () => {
    const wrapper = mount(Skeleton, { props: { variant: 'rect' } })
    expect(wrapper.find('.sk-sr-only').text()).toBe('Lade…')
  })
})
