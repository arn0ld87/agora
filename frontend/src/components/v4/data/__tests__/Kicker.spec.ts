/**
 * Kicker — Tests
 * Slice UI-C · 2026-05-15
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Kicker from '../Kicker.vue'

describe('Kicker', () => {
  it('Test 1: Default-Mount zeigt nur Text-Slot, keinen Num-Prefix', () => {
    const wrapper = mount(Kicker, {
      slots: { default: 'Abschnitt' },
    })

    expect(wrapper.find('.kk-root').exists()).toBe(true)
    expect(wrapper.find('.kk-text').text()).toBe('Abschnitt')
    expect(wrapper.find('.kk-num').exists()).toBe(false)
  })

  it('Test 2: num-Prop fügt Numerierung als Präfix ein', () => {
    const wrapper = mount(Kicker, {
      props: { num: '03' },
      slots: { default: 'Persona-Quoten' },
    })

    const num = wrapper.find('.kk-num')
    expect(num.exists()).toBe(true)
    expect(num.text()).toBe('№ 03 —')
  })

  it('Test 3: num=null oder leer rendert keinen Präfix', () => {
    const wrapperNull = mount(Kicker, { props: { num: null }, slots: { default: 'X' } })
    const wrapperEmpty = mount(Kicker, { props: { num: '' }, slots: { default: 'Y' } })

    expect(wrapperNull.find('.kk-num').exists()).toBe(false)
    expect(wrapperEmpty.find('.kk-num').exists()).toBe(false)
  })

  it('Test 4: accent-Prop trägt accent-Klasse', () => {
    const wrapper = mount(Kicker, {
      props: { accent: true },
      slots: { default: 'Wichtig' },
    })

    expect(wrapper.find('.kk-root--accent').exists()).toBe(true)
  })

  it('Test 5: num als number wird gerendert', () => {
    const wrapper = mount(Kicker, {
      props: { num: 7 },
      slots: { default: 'Sektion sieben' },
    })

    expect(wrapper.find('.kk-num').text()).toBe('№ 7 —')
  })
})
