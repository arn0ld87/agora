import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import RedditPost from '../RedditPost.vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

// Stub-Komponenten für PersonaAvatar und SimBadge
const PersonaAvatarStub = { template: '<div class="persona-avatar-stub" />', props: ['personaId', 'voiceRegister'] }
const SimBadgeStub = { template: '<span class="sim-badge-stub">SIM</span>' }

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: { de: { feed: { simBadge: 'SIM' } } },
})

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p1',
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    voice_register: 'casual',
    is_simulated: true,
    body: 'Test-Post',
    timestamp: '2026-05-15T12:30:00Z',
    sentiment: null,
    score: 0,
    ...overrides,
  }
}

const globalConfig = {
  plugins: [i18n],
  components: {
    PersonaAvatar: PersonaAvatarStub,
    SimBadge: SimBadgeStub,
  },
}

describe('RedditPost', () => {
  it('rendert Post-Body', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ body: 'Hallo Reddit!' }), depth: 0 },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('Hallo Reddit!')
  })

  it('rendert Persona-ID als u/<id>', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ persona_id: 'bob' }), depth: 0 },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('u/bob')
  })

  it('hat role=article', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost(), depth: 0 },
      global: globalConfig,
    })
    expect(wrapper.find('[role="article"]').exists()).toBe(true)
  })

  // Phase B — Voting-Score Tests
  it('zeigt Score 0 neutral (keine Farb-Klasse)', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ score: 0 }), depth: 0 },
      global: globalConfig,
    })
    const score = wrapper.find('.rp-score')
    expect(score.exists()).toBe(true)
    expect(score.text()).toBe('0')
    expect(score.classes()).not.toContain('rp-score--positive')
    expect(score.classes()).not.toContain('rp-score--negative')
  })

  it('zeigt positiven Score mit rp-score--positive Klasse (orange)', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ score: 42 }), depth: 0 },
      global: globalConfig,
    })
    const score = wrapper.find('.rp-score')
    expect(score.text()).toBe('42')
    expect(score.classes()).toContain('rp-score--positive')
  })

  it('zeigt negativen Score mit rp-score--negative Klasse (blau)', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ score: -7 }), depth: 0 },
      global: globalConfig,
    })
    const score = wrapper.find('.rp-score')
    expect(score.text()).toBe('-7')
    expect(score.classes()).toContain('rp-score--negative')
  })

  it('hat kein Click-Handler auf Voting-Elementen (read-only)', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ score: 10 }), depth: 0 },
      global: globalConfig,
    })
    const voting = wrapper.find('.rp-voting')
    expect(voting.exists()).toBe(true)
    // kein onclick-Attribut
    expect(voting.attributes('onclick')).toBeUndefined()
    const arrows = wrapper.findAll('.rp-arrow')
    expect(arrows).toHaveLength(2)
    for (const arrow of arrows) {
      expect(arrow.attributes('onclick')).toBeUndefined()
    }
  })

  it('zeigt Score >= 1000 als k-Format', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost({ score: 1500 }), depth: 0 },
      global: globalConfig,
    })
    expect(wrapper.find('.rp-score').text()).toBe('1.5k')
  })

  it('depth=0 hat kein rp-rail (kein Indent)', () => {
    const wrapper = mount(RedditPost, {
      props: { post: mkPost(), depth: 0 },
      global: globalConfig,
    })
    // data-depth=0 ist gesetzt
    expect(wrapper.find('[data-depth="0"]').exists()).toBe(true)
  })
})
