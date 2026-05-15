import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import SimulationPulseBar from '../SimulationPulseBar.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      feed: {
        live: 'Live',
        activity: 'Posts/min',
      },
    },
  },
})

describe('SimulationPulseBar', () => {
  it('zeigt Reddit- und Twitter-Count', () => {
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 3.5, redditCount: 5, twitterCount: 3 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Reddit: 5')
    expect(wrapper.text()).toContain('Twitter: 3')
  })

  it('zeigt activity rate gerundet auf 1 Dezimalstelle', () => {
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 12.347, redditCount: 0, twitterCount: 0 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('12.3')
  })

  it('zeigt "< 0.1" wenn activity rate unter 0.1', () => {
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 0.05, redditCount: 0, twitterCount: 0 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('< 0.1')
  })

  it('hat role=status für Screenreader', () => {
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 0, redditCount: 0, twitterCount: 0 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
  })
})
