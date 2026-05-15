import { describe, it, expect, beforeEach } from 'vitest'
import { useSimFeed, resetSimFeedStore } from '../useSimFeed'
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
    expect(feed.redditPosts.value).toHaveLength(1)
    expect(feed.twitterPosts.value).toHaveLength(0)
  })

  it('post_created mit platform=twitter landet in twitterPosts', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-1' }))
    expect(feed.twitterPosts.value).toHaveLength(1)
    expect(feed.redditPosts.value).toHaveLength(0)
  })

  it('Reddit-Posts mit parent_post_id werden als Reply-Tree gruppiert', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-1', parent_post_id: null }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-2', parent_post_id: 'p-1' }))
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'p-3', parent_post_id: 'p-1' }))

    const tree = feed.redditTree.value
    expect(tree).toHaveLength(1)
    expect(tree[0].children).toHaveLength(2)
    expect(tree[0].children.map((c) => c.post_id)).toEqual(['p-2', 'p-3'])
  })

  it('Posts werden nicht dupliziert bei doppeltem post_id', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ post_id: 'p-1' }))
    feed.ingest(mkPost({ post_id: 'p-1' }))
    expect(feed.redditPosts.value).toHaveLength(1)
  })

  it('Twitter sortiert nach timestamp DESC (neueste oben)', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-old', timestamp: '2026-05-15T12:00:00Z' }))
    feed.ingest(mkPost({ platform: 'twitter', post_id: 'p-new', timestamp: '2026-05-15T12:01:00Z' }))
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
})
