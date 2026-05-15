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
        sentimentBar: 'Sentiment-Verlauf',
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
    voice_register: 'casual',
    is_simulated: true,
    body: 'Test',
    timestamp: '2026-05-15T12:00:00Z',
    sentiment: null,
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

  // Phase B — Heatbar-Tests
  it('rendert sentiment-negative Klasse für Sentiment < -0.33', () => {
    const posts = [mkPost({ sentiment: -0.8 }), mkPost({ sentiment: -0.5 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    const pulses = wrapper.findAll('.spb-pulse.sentiment-negative')
    expect(pulses).toHaveLength(2)
  })

  it('rendert sentiment-positive Klasse für Sentiment > 0.33', () => {
    const posts = [mkPost({ sentiment: 0.9 }), mkPost({ sentiment: 0.5 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    const pulses = wrapper.findAll('.spb-pulse.sentiment-positive')
    expect(pulses).toHaveLength(2)
  })

  it('rendert sentiment-neutral Klasse für Sentiment in [-0.33, 0.33]', () => {
    const posts = [mkPost({ sentiment: 0.0 }), mkPost({ sentiment: 0.2 }), mkPost({ sentiment: -0.1 })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 1, redditCount: 3, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    const pulses = wrapper.findAll('.spb-pulse.sentiment-neutral')
    expect(pulses).toHaveLength(3)
  })

  it('rendert sentiment-null Klasse wenn sentiment null (Sentiment-Service inaktiv)', () => {
    const posts = [mkPost({ sentiment: null }), mkPost({ sentiment: null })]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 0, redditCount: 2, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    const pulses = wrapper.findAll('.spb-pulse.sentiment-null')
    expect(pulses).toHaveLength(2)
  })

  it('gemischte Sentiments werden korrekt klassifiziert', () => {
    const posts = [
      mkPost({ sentiment: -0.8 }),
      mkPost({ sentiment: 0.1 }),
      mkPost({ sentiment: 0.7 }),
      mkPost({ sentiment: null }),
    ]
    const wrapper = mount(SimulationPulseBar, {
      props: { activityRate: 2, redditCount: 4, twitterCount: 0, recentPosts: posts },
      global: { plugins: [i18n] },
    })
    expect(wrapper.findAll('.sentiment-negative')).toHaveLength(1)
    expect(wrapper.findAll('.sentiment-neutral')).toHaveLength(1)
    expect(wrapper.findAll('.sentiment-positive')).toHaveLength(1)
    expect(wrapper.findAll('.sentiment-null')).toHaveLength(1)
  })
})
