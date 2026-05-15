import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import TwitterPost from '../TwitterPost.vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: { de: { feed: { simBadge: 'SIM' } } },
})

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'twitter',
    persona_id: 'testuser',
    voice_register: 'casual',
    is_simulated: true,
    body: 'Test-Post-Inhalt',
    timestamp: '2026-05-15T14:30:00Z',
    score: 0,
    ...overrides,
  }
}

describe('TwitterPost', () => {
  it('rendert @handle aus persona_id', () => {
    const wrapper = mount(TwitterPost, {
      props: { post: mkPost() },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('@testuser')
  })

  it('zeigt SIM-Badge wenn is_simulated=true', () => {
    const wrapper = mount(TwitterPost, {
      props: { post: mkPost({ is_simulated: true }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.sim-badge').exists()).toBe(true)
  })

  it('zeigt kein SIM-Badge wenn is_simulated=false', () => {
    const wrapper = mount(TwitterPost, {
      props: { post: mkPost({ is_simulated: false }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.sim-badge').exists()).toBe(false)
  })

  it('rendert Post-Body', () => {
    const wrapper = mount(TwitterPost, {
      props: { post: mkPost({ body: 'Hallo Welt!' }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Hallo Welt!')
  })
})
