import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RedditRow from '../RedditRow.vue'
import { buildRedditList } from '@/composables/run/simulation/threads'
import { i18n, makePost, makeRouter } from './fixtures'

describe('RedditRow', () => {
  const posts = [
    makePost({ post_id: 'reddit:1', platform: 'reddit', score: 12 }),
    makePost({ post_id: 'reddit:comment:2', platform: 'reddit', kind: 'comment', parent_post_id: 'reddit:1', root_post_id: 'reddit:1' }),
  ]

  function mountRow() {
    const entry = buildRedditList(posts)[0]
    return mount(RedditRow, {
      props: { entry, to: { name: 'RunSimulationPost', params: { simulationId: 'sim_1', postId: 'reddit:1' } } },
      global: { plugins: [makeRouter(), i18n] },
    })
  }

  it('zeigt Stimmen- und Kommentarzahl, SIM-Kennzeichen und die Adresse', () => {
    const w = mountRow()
    expect(w.get('[data-testid="count-votes"]').text()).toBe('Stimmen: 12')
    expect(w.get('[data-testid="count-comments"]').text()).toBe('ein Kommentar')
    expect(w.get('[data-testid="post-sim"] .sr-only').text()).toBe('synthetische Äußerung')
    expect(w.get('[data-testid="reddit-row-link"]').attributes('href')).toContain('/post/reddit:1')
  })

  it('öffnet per Klick und Enter', async () => {
    const w = mountRow()
    const row = w.get('[data-testid="reddit-row"]')
    await row.trigger('click')
    await row.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('open')).toHaveLength(2)
  })
})
