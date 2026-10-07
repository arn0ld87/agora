import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TwitterCard from '../TwitterCard.vue'
import { buildTwitterTimeline } from '@/composables/run/simulation/threads'
import { i18n, makePost, makeRouter } from './fixtures'

function mountCard(posts = [makePost({ post_id: 'twitter:1', like_count: 7, round_num: 3 })], index = 0) {
  const router = makeRouter()
  const entry = buildTwitterTimeline(posts)[index]
  const w = mount(TwitterCard, {
    props: {
      entry,
      to: { name: 'RunSimulationPost', params: { simulationId: 'sim_1', postId: entry.post.post_id } },
    },
    global: { plugins: [router, i18n] },
  })
  return { w, router }
}

describe('TwitterCard', () => {
  it('zeigt Name, Text, Runde und das SIM-Kennzeichen mit zugänglichem Text', () => {
    const { w } = mountCard()
    expect(w.text()).toContain('Anna')
    expect(w.text()).toContain('Text twitter:1')
    expect(w.text()).toContain('Runde 3')
    const sim = w.get('[data-testid="post-sim"]')
    expect(sim.text()).toContain('SIM')
    expect(sim.get('.sr-only').text()).toBe('synthetische Äußerung')
  })

  it('zeigt Zähler für Antworten, Weiterleitungen und Zustimmung als Text', () => {
    const posts = [
      makePost({ post_id: 'twitter:1', like_count: 7 }),
      makePost({ post_id: 'twitter:2', parent_post_id: 'twitter:1', kind: 'comment', root_post_id: 'twitter:1' }),
      makePost({ post_id: 'twitter:3', parent_post_id: 'twitter:1', kind: 'comment', root_post_id: 'twitter:1' }),
      makePost({ post_id: 'twitter:4', kind: 'repost', reposted_post_id: 'twitter:1', body: '' }),
    ]
    const { w } = mountCard(posts)
    expect(w.get('[data-testid="twitter-card-counts"]').attributes('aria-label')).toBe('Zähler')
    expect(w.get('[data-testid="count-replies"]').text()).toBe('2 Antworten')
    expect(w.get('[data-testid="count-reposts"]').text()).toBe('eine Weiterleitung')
    expect(w.get('[data-testid="count-likes"]').text()).toBe('7 Zustimmungen')
  })

  it('bettet ein Zitat ein', () => {
    const posts = [
      makePost({ post_id: 'twitter:1', body: 'Original' }),
      makePost({ post_id: 'twitter:2', kind: 'quote', quoted_post_id: 'twitter:1', body: 'Meine Sicht' }),
    ]
    const { w } = mountCard(posts, 1)
    expect(w.get('[data-testid="twitter-card-quote"]').text()).toContain('Original')
  })

  it('kennzeichnet Reposts ohne Original sichtbar', () => {
    const posts = [makePost({ post_id: 'twitter:9', kind: 'repost', reposted_post_id: 'twitter:0', body: '' })]
    const { w } = mountCard(posts)
    expect(w.get('[data-testid="twitter-card-repost"]').text()).toContain('Weiterleitung')
    expect(w.find('[data-testid="twitter-card-reference-missing"]').exists()).toBe(true)
  })

  it('öffnet per Klick und Enter; Fokus meldet die Persona; Link trägt die Adresse mit Doppelpunkten', async () => {
    const { w } = mountCard()
    const card = w.get('[data-testid="twitter-card"]')
    expect(card.attributes('tabindex')).toBe('0')
    await card.trigger('click')
    await card.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('open')).toHaveLength(2)
    await card.trigger('focus')
    expect(w.emitted('focus')?.[0]).toEqual(['0'])
    expect(w.get('[data-testid="twitter-card-link"]').attributes('href')).toContain('/post/twitter:1')
  })
})
