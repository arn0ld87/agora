/**
 * FeedItem — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.4.
 * Deckt die Kind-abhaengige Kontext-Zeile, die Degradations-Wortlaute
 * (kein stiller Fallback auf "unbekannt") und die Tastatur-Aktivierung ab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import { useSimFeed, resetSimFeedStore } from '@/composables/useSimFeed'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

import FeedItem from '../FeedItem.vue'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-fi',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'twitter',
    persona_id: 'alice',
    persona_name: 'Alice',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'hallo welt',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    kind: 'post',
    ...overrides,
  }
}

describe('FeedItem', () => {
  beforeEach(() => {
    resetSimFeedStore('sim-fi')
  })

  it('kind=post rendert ohne Kontext-Zeile', () => {
    const w = mount(FeedItem, { props: { post: mkPost() } })
    expect(w.find('.fi-context').exists()).toBe(false)
    expect(w.text()).toContain('hallo welt')
  })

  it('kind=reddit rendert RedditPost-Body (Voting-Bar)', () => {
    const w = mount(FeedItem, { props: { post: mkPost({ platform: 'reddit' }) } })
    expect(w.find('.rp-root').exists()).toBe(true)
  })

  it('kind=comment mit parent_persona_name zeigt replyTo-Kontext', () => {
    const w = mount(FeedItem, {
      props: { post: mkPost({ kind: 'comment', parent_persona_name: 'Bob', parent_post_id: 'p-0' }) },
    })
    expect(w.get('.fi-context').text()).toBe('feed.replyTo')
  })

  it('kind=comment ohne parent_persona_name zeigt Degradations-Wortlaut, kein "unbekannt"', () => {
    const w = mount(FeedItem, {
      props: { post: mkPost({ kind: 'comment', parent_persona_name: null, parent_post_id: 'p-0' }) },
    })
    expect(w.get('.fi-context').text()).toBe('feed.replyToUnknown')
  })

  it('kind=quote mit quote_body zeigt den Zitat-Text', () => {
    const w = mount(FeedItem, {
      props: { post: mkPost({ kind: 'quote', quote_body: 'zitierter text', quoted_post_id: 'p-9' }) },
    })
    expect(w.get('.fi-quote-body').text()).toBe('zitierter text')
  })

  it('kind=quote ohne quote_body zeigt "Zitat nicht mehr auffindbar"', () => {
    const w = mount(FeedItem, {
      props: { post: mkPost({ kind: 'quote', quote_body: null, quoted_post_id: 'p-9' }) },
    })
    expect(w.get('.fi-quote-missing').text()).toBe('feed.quoteMissing')
  })

  it('kind=repost mit aufloesbarer Quelle rendert den Ursprungsbeitrag verschachtelt', () => {
    const feed = useSimFeed('sim-fi')
    feed.ingest(mkPost({ post_id: 'origin', body: 'original text' }))
    feed.flushPending()
    const w = mount(FeedItem, {
      props: { post: mkPost({ post_id: 'p-repost', kind: 'repost', reposted_post_id: 'origin' }) },
    })
    expect(w.get('.fi-repost-body').text()).toContain('original text')
  })

  it('kind=repost ohne aufloesbare Quelle zeigt "Bezug nicht erfasst"', () => {
    const w = mount(FeedItem, {
      props: { post: mkPost({ kind: 'repost', reposted_post_id: 'unknown-id' }) },
    })
    expect(w.get('.fi-repost-missing').text()).toBe('feed.repostSourceMissing')
  })

  it('Enter auf dem Artikel emittiert openThread mit der Strang-Wurzel', async () => {
    const w = mount(FeedItem, {
      props: { post: mkPost({ post_id: 'p-2', root_post_id: 'root-9' }) },
    })
    await w.get('.fi-root').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('openThread')?.[0]).toEqual(['root-9'])
  })

  it('Space auf dem Artikel emittiert openThread', async () => {
    const w = mount(FeedItem, { props: { post: mkPost({ post_id: 'p-3' }) } })
    await w.get('.fi-root').trigger('keydown', { key: ' ' })
    expect(w.emitted('openThread')?.[0]).toEqual(['p-3'])
  })

  it('isNew=true rendert den Neu-Marker', () => {
    const w = mount(FeedItem, { props: { post: mkPost(), isNew: true } })
    expect(w.find('.fi-new-dot').exists()).toBe(true)
  })
})
