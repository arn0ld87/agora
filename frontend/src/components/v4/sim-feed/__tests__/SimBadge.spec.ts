import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import SimBadge from '../SimBadge.vue'

describe('SimBadge', () => {
  it('rendert SIM-Label wenn kein i18n-Key vorhanden', () => {
    const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: {} } })
    const wrapper = mount(SimBadge, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toBe('SIM')
  })

  it('rendert i18n-Key wenn feed.simBadge vorhanden', () => {
    const i18n = createI18n({
      legacy: false,
      locale: 'de',
      messages: { de: { feed: { simBadge: 'SIM' } } },
    })
    const wrapper = mount(SimBadge, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toBe('SIM')
  })
})
