import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import RedditThread from '../RedditThread.vue'
import type { RedditNode } from '@/composables/useSimFeed'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      feed: { simBadge: 'SIM', showMoreReplies: '{count} weitere Replies anzeigen' },
    },
  },
})

function mkNode(overrides: Partial<RedditNode> = {}): RedditNode {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'root',
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    voice_register: 'casual',
    is_simulated: true,
    body: 'Root-Post',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    children: [],
    ...overrides,
  }
}

describe('RedditThread', () => {
  it('rendert Root-Post', () => {
    const node = mkNode({ body: 'Hallo Reddit!' })
    const wrapper = mount(RedditThread, {
      props: { node },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Hallo Reddit!')
  })

  it('rendert verschachtelte Kinder (depth 1)', () => {
    const node = mkNode({
      post_id: 'root',
      body: 'Root',
      children: [
        mkNode({ post_id: 'child-1', parent_post_id: 'root', body: 'Antwort 1' }),
        mkNode({ post_id: 'child-2', parent_post_id: 'root', body: 'Antwort 2' }),
      ],
    })
    const wrapper = mount(RedditThread, {
      props: { node, depth: 0 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Antwort 1')
    expect(wrapper.text()).toContain('Antwort 2')
  })

  it('zeigt show-more Button wenn MAX_DEPTH überschritten und Kinder vorhanden', () => {
    const deepChild = mkNode({
      post_id: 'deep',
      body: 'Tief',
      children: [mkNode({ post_id: 'deeper', body: 'Tiefer' })],
    })
    const wrapper = mount(RedditThread, {
      props: { node: deepChild, depth: 4 }, // depth >= MAX_DEPTH=4
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.rt-show-more').exists()).toBe(true)
  })
})
