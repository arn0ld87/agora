/**
 * Chart — Tests
 * Slice UI-B · 2026-05-15
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Chart from '../Chart.vue'

describe('Chart', () => {
  it('Test 1: Pflicht-title wird gerendert, optional Description', () => {
    const wrapper = mount(Chart, {
      props: { title: 'Risiko-Verlauf' },
      slots: { default: '<svg data-testid="svg"/>' },
    })

    expect(wrapper.find('.ch-title').text()).toBe('Risiko-Verlauf')
    expect(wrapper.find('.ch-description').exists()).toBe(false)
    expect(wrapper.find('[data-testid="svg"]').exists()).toBe(true)
  })

  it('Test 2: description, timeRange, unit, interpretation werden gerendert', () => {
    const wrapper = mount(Chart, {
      props: {
        title: 'Mood-Verlauf',
        description: 'Aggregiert über alle Personas',
        timeRange: 'Jan – Jun 2026',
        unit: 'Index 0–100',
        interpretation: 'Stimmung kippt bei fehlender Freitags-Erreichbarkeit.',
      },
      slots: { default: '<div/>' },
    })

    expect(wrapper.find('.ch-description').text()).toBe('Aggregiert über alle Personas')
    expect(wrapper.find('.ch-meta').exists()).toBe(true)
    expect(wrapper.text()).toContain('Jan – Jun 2026')
    expect(wrapper.text()).toContain('Index 0–100')
    expect(wrapper.find('.ch-interpretation').text()).toContain('Stimmung kippt')
  })

  it('Test 3: ohne timeRange + unit ist Meta-Zeile unsichtbar', () => {
    const wrapper = mount(Chart, {
      props: { title: 'X' },
      slots: { default: '<div/>' },
    })

    expect(wrapper.find('.ch-meta').exists()).toBe(false)
  })

  it('Test 4: toolbar-Slot wird gerendert', () => {
    const wrapper = mount(Chart, {
      props: { title: 'X' },
      slots: {
        default: '<div/>',
        toolbar: '<button data-testid="range-picker">Letzte 7 Tage</button>',
      },
    })

    expect(wrapper.find('.ch-toolbar').exists()).toBe(true)
    expect(wrapper.find('[data-testid="range-picker"]').exists()).toBe(true)
  })

  it('Test 5: loading rendert Skeleton statt Default-Slot', () => {
    const wrapper = mount(Chart, {
      props: { title: 'X', loading: true },
      slots: { default: '<div data-testid="real-chart"/>' },
    })

    expect(wrapper.find('.ch-loading').exists()).toBe(true)
    expect(wrapper.findAll('.ch-skeleton-bar')).toHaveLength(3)
    expect(wrapper.find('[data-testid="real-chart"]').exists()).toBe(false)
  })

  it('Test 6: legend-Slot wird gerendert', () => {
    const wrapper = mount(Chart, {
      props: { title: 'X' },
      slots: {
        default: '<div/>',
        legend: '<span data-testid="leg">Personas</span>',
      },
    })

    expect(wrapper.find('.ch-legend').exists()).toBe(true)
    expect(wrapper.find('[data-testid="leg"]').exists()).toBe(true)
  })

  it('Test 7: minHeight wird auf ch-canvas durchgereicht', () => {
    const wrapper = mount(Chart, {
      props: { title: 'X', minHeight: '400px' },
      slots: { default: '<div/>' },
    })

    const canvas = wrapper.find('.ch-canvas')
    expect(canvas.attributes('style')).toContain('min-height: 400px')
  })
})
