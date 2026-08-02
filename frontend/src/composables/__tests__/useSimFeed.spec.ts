import { describe, it, expect, beforeEach } from 'vitest'
import { useSimFeed, clearSimFeed, resetSimFeedStore, MAX_POSTS_PER_FEED } from '../useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    voice_register: 'casual',
    is_simulated: true,
    body: 'hi',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

describe('useSimFeed', () => {
  beforeEach(() => {
    resetSimFeedStore('sim-1')
    resetSimFeedStore('sim-2')
  })

  it('Default: leere Reddit- und Twitter-Listen', () => {
    const feed = useSimFeed('sim-1')
    expect(feed.redditPosts.value).toEqual([])
    expect(feed.twitterPosts.value).toEqual([])
  })

  it('post_created mit platform=reddit landet in redditPosts', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-1' }))
    feed.flushPending()
    expect(feed.redditPosts.value).toHaveLength(1)
    expect(feed.twitterPosts.value).toHaveLength(0)
  })

  it('post_created mit platform=twitter landet in twitterPosts', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-1' }))
    feed.flushPending()
    expect(feed.twitterPosts.value).toHaveLength(1)
    expect(feed.redditPosts.value).toHaveLength(0)
  })

  it('Reddit-Posts mit parent_post_id werden als Reply-Tree gruppiert', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-1', parent_post_id: null }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-2', parent_post_id: 'p-1' }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-3', parent_post_id: 'p-1' }))
    feed.flushPending()

    const tree = feed.redditTree.value
    expect(tree).toHaveLength(1)
    expect(tree[0].children).toHaveLength(2)
    expect(tree[0].children.map((c) => c.post_id)).toEqual(['p-2', 'p-3'])
  })

  it('Posts werden nicht dupliziert bei doppeltem post_id', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ post_id: 'p-1' }))
    feed.ingest(mkPost({ post_id: 'p-1' }))
    feed.flushPending()
    expect(feed.redditPosts.value).toHaveLength(1)
  })

  it('Twitter sortiert nach timestamp DESC (neueste oben)', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-old', timestamp: '2026-05-15T12:00:00Z' }))
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-new', timestamp: '2026-05-15T12:01:00Z' }))
    feed.flushPending()
    expect(feed.twitterPosts.value.map((p) => p.post_id)).toEqual(['p-new', 'p-old'])
  })

  it('activityRate berechnet Posts/min (EMA über last 30 Posts)', () => {
    const feed = useSimFeed('sim-1')
    for (let i = 0; i < 5; i++) {
      feed.ingest(
        mkPost({
          post_id: `p-${i}`,
          timestamp: new Date(Date.now() - (5 - i) * 1000).toISOString(),
        }),
      )
    }
    feed.flushPending()
    expect(feed.activityRate.value).toBeGreaterThan(0)
  })

  it('clear() leert beide Listen', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-r' }))
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-x' }))
    feed.clear()
    expect(feed.redditPosts.value).toEqual([])
    expect(feed.twitterPosts.value).toEqual([])
  })

  it('Posts anderer simulation_id werden ignoriert', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ simulation_id: 'sim-2', post_id: 'p-other' }))
    expect(feed.redditPosts.value).toHaveLength(0)
  })

  it('clearSimFeed: Store wird aus Map entfernt — neuer useSimFeed-Aufruf liefert frischen State', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ post_id: 'p-before' }))
    feed.flushPending()
    expect(feed.redditPosts.value).toHaveLength(1)

    clearSimFeed('sim-1')

    // Nach clearSimFeed erstellt useSimFeed einen frischen Store
    const fresh = useSimFeed('sim-1')
    expect(fresh.redditPosts.value).toHaveLength(0)
  })

  it('LRU-Limit: bei > 10 simulationIds wird ältester evicted', () => {
    // Alle 10 füllen
    for (let i = 0; i < 10; i++) {
      resetSimFeedStore(`lru-${i}`)
      useSimFeed(`lru-${i}`)
    }
    // Beim 11. Eintrag wird lru-0 evicted
    resetSimFeedStore('lru-10')
    const feed11 = useSimFeed('lru-10')
    feed11.ingest(mkPost({ simulation_id: 'lru-10', post_id: 'p-new' }))
    feed11.flushPending()
    expect(feed11.redditPosts.value).toHaveLength(1)
    // lru-0 wurde aus dem Store entfernt — neuer Aufruf erstellt frischen State
    const afterEvict = useSimFeed('lru-0')
    expect(afterEvict.redditPosts.value).toHaveLength(0)
  })

  // Slice 9 · #1007 — Ringpuffer + rAF-Batching

  it('ingest + flushPending: nimmt Posts auf und dedupliziert per post_id', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ post_id: 'p-dup' }))
    feed.ingest(mkPost({ post_id: 'p-dup' }))
    feed.flushPending()
    expect(feed.redditPosts.value).toHaveLength(1)
  })

  it('ingest: Posts einer fremden simulation_id werden ignoriert', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ simulation_id: 'sim-fremd', post_id: 'p-fremd' }))
    feed.flushPending()
    expect(feed.redditPosts.value).toHaveLength(0)
  })

  it('Ringpuffer: MAX_POSTS_PER_FEED + 50 Posts überschreiten das Limit nicht und behalten die neuesten', () => {
    const feed = useSimFeed('sim-1')
    const total = MAX_POSTS_PER_FEED + 50
    const base = Date.parse('2026-08-02T10:00:00+00:00')
    const posts = Array.from({ length: total }, (_, i) =>
      mkPost({
        platform: 'reddit',
        post_id: `p-${i}`,
        timestamp: new Date(base + i * 1000).toISOString(),
      }),
    )
    feed.ingestMany(posts)

    expect(feed.redditPosts.value.length).toBe(MAX_POSTS_PER_FEED)
    const ids = feed.redditPosts.value.map((p) => p.post_id)
    // Die 50 ältesten (p-0 .. p-49) sind aus dem Ringpuffer gefallen.
    expect(ids).not.toContain('p-0')
    expect(ids).not.toContain('p-49')
    // Die neuesten Posts sind erhalten.
    expect(ids).toContain(`p-${total - 1}`)
    expect(ids).toContain('p-50')
  })

  it('redditTree: hängt Replies unter ihren parent_post_id, Posts ohne Parent sind Top-Level-Wurzeln', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'root-a', parent_post_id: null }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'root-b', parent_post_id: null }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'reply-a1', parent_post_id: 'root-a' }))
    feed.flushPending()

    const tree = feed.redditTree.value
    expect(tree.map((n) => n.post_id).sort()).toEqual(['root-a', 'root-b'])

    const rootA = tree.find((n) => n.post_id === 'root-a')!
    expect(rootA.children.map((c) => c.post_id)).toEqual(['reply-a1'])

    const rootB = tree.find((n) => n.post_id === 'root-b')!
    expect(rootB.children).toEqual([])
  })
})
