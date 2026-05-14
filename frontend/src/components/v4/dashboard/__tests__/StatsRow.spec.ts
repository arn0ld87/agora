import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatsRow from '../StatsRow.vue'
import { makeI18n } from './dashTestHelpers'

describe('StatsRow', () => {
  it('rendert vier Mikro-Kennzahlen mit Werten', () => {
    const w = mount(StatsRow, {
      props: { activeRuns: 3, completedToday: 7, avgConfidence: 0.62, personas: 24 },
      global: { plugins: [makeI18n()] },
    })
    const cells = w.findAll('.stats-cell__value')
    expect(cells).toHaveLength(4)
    expect(cells[0].text()).toBe('3')
    expect(cells[1].text()).toBe('7')
    expect(cells[2].text()).toBe('62%')
    expect(cells[3].text()).toBe('24')
  })

  it('dimmt avgConfidence wenn null', () => {
    const w = mount(StatsRow, {
      props: { activeRuns: 0, completedToday: 0, avgConfidence: null, personas: 0 },
      global: { plugins: [makeI18n()] },
    })
    expect(w.find('.stats-cell__dim').exists()).toBe(true)
  })
})
