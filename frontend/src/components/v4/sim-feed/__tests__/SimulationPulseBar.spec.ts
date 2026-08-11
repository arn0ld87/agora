import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import SimulationPulseBar from '../SimulationPulseBar.vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      feed: {
        live: 'Live',
        activity: 'Posts/min',
        resonanceBar: 'Resonanz-Verlauf',
      },
    },
  },
})

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p1',
    parent_post_id: null,
    platform: 'reddit',
persona_id: 'persona-1',
    persona_name: 'Test Persona',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'Test',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

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

  // #1209 5b — die Leiste färbt nach Voting-Score statt nach einem nie
  // erhobenen Sentiment.
  it('rendert score-negative Klasse bei negativem Score', () => {
    const posts = [mkPost({ score: -4 }), mkPost({ score: -1 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.spb-pulse.score-negative')).toHaveLength(2)
  })

  it('rendert score-positive Klasse bei positivem Score', () => {
    const posts = [mkPost({ score: 9 }), mkPost({ score: 1 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.spb-pulse.score-positive')).toHaveLength(2)
  })

  it('rendert score-neutral Klasse bei Score 0', () => {
    const posts = [mkPost({ score: 0 }), mkPost({ score: 0 }), mkPost({ score: 0 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 3, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.spb-pulse.score-neutral')).toHaveLength(3)
  })

  it('dimmt die Leiste, solange kein Post Resonanz hat', () => {
    const posts = [mkPost({ score: 0 }), mkPost({ score: 0 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 0, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.spb-pulse--dim')).toHaveLength(2)
  })

  it('dimmt nicht mehr, sobald ein Post Resonanz hat', () => {
    const posts = [mkPost({ score: 0 }), mkPost({ score: 3 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.spb-pulse--dim')).toHaveLength(0)
  })

  it('gemischte Scores werden korrekt klassifiziert', () => {
    const posts = [mkPost({ score: -8 }), mkPost({ score: 0 }), mkPost({ score: 7 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 2, redditCount: 3, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.score-negative')).toHaveLength(1)
    expect(wrapper.findAll('.score-neutral')).toHaveLength(1)
    expect(wrapper.findAll('.score-positive')).toHaveLength(1)
  })
})
