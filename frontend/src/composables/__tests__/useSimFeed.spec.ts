import { describe, it, expect, beforeEach } from 'vitest'
import {
  useSimFeed,
  clearSimFeed,
  resetSimFeedStore,
  MAX_POSTS_PER_FEED,
  parentIdOf,
  buildThreadSummaries,
  collectThreadNodes,
} from '../useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'reddit',
persona_id: 'alice',
    persona_name: 'Test Persona',
    voice_register: 'neutral-de',
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

  // PR-Review #1010 (Codex P1): ein Hintergrund-Tab bekommt keine Animation
  // Frames, waehrend SSE weiterhin ingest() aufruft. Ohne Schranke im Puffer
  // waere `pending` die neue unbegrenzt wachsende Struktur — der Ringpuffer
  // liefe leer, weil er erst beim Flush greift.
  it('Ringpuffer greift auch ohne Animation Frame (Hintergrund-Tab)', () => {
    const originalRaf = globalThis.requestAnimationFrame
    // rAF, das nie zurueckruft — exakt das Verhalten eines inaktiven Tabs.
    globalThis.requestAnimationFrame = () => 0
    try {
      const feed = useSimFeed('sim-1')
      const total = MAX_POSTS_PER_FEED + 50
      for (let i = 0; i < total; i++) {
        feed.ingest(mkPost({ platform: 'reddit', post_id: `bg-${i}` }))
      }

      // Bewusst OHNE flushPending(): der Puffer muss sich selbst begrenzt
      // haben. Ohne die Schranke laegen hier alle 550 Posts noch in
      // `pending`, all.value waere leer und der Ringpuffer haette nie
      // gegriffen — ein nachtraeglicher Flush wuerde das verdecken.
      expect(feed.redditPosts.value.length).toBe(MAX_POSTS_PER_FEED)

      // Der Rest folgt beim naechsten Flush, die Obergrenze haelt weiterhin.
      feed.flushPending()
      expect(feed.redditPosts.value.length).toBe(MAX_POSTS_PER_FEED)
      const ids = feed.redditPosts.value.map((p) => p.post_id)
      expect(ids).not.toContain('bg-0')
      expect(ids).toContain(`bg-${total - 1}`)
    } finally {
      globalThis.requestAnimationFrame = originalRaf
    }
  })

  // PR-Review #1010 (CodeRabbit): ingestMany() darf einen bereits gepufferten
  // Post nicht ueberholen, sonst steht all.value nicht mehr in
  // Eingangsreihenfolge — was Ringpuffer-Eviction und activityRate verfaelscht.
  it('Reihenfolge bleibt erhalten, wenn ingest() und ingestMany() sich mischen', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ platform: 'reddit', post_id: 'first' }))
    feed.ingestMany([mkPost({ platform: 'reddit', post_id: 'second' })])
    feed.flushPending()

    expect(feed.redditPosts.value.map((p) => p.post_id)).toEqual(['first', 'second'])
  })

  // Slice UI-2b (#1713) — flatTimeline, byId, parentIdOf

  it('flatTimeline: sortiert beide Plattformen chronologisch aufsteigend', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(
      mkPost({ platform: 'twitter', post_id: 't-new', timestamp: '2026-05-15T12:02:00Z' }),
    )
    feed.ingest(
      mkPost({ platform: 'reddit', post_id: 'r-old', timestamp: '2026-05-15T12:00:00Z' }),
    )
    feed.flushPending()
    expect(feed.flatTimeline.value.map((p) => p.post_id)).toEqual(['r-old', 't-new'])
  })

  it('byId: loest einen bekannten Post auf, liefert undefined fuer unbekannte post_id', () => {
    const feed = useSimFeed('sim-1')
    feed.ingest(mkPost({ post_id: 'p-known' }))
    feed.flushPending()
    expect(feed.byId('p-known')?.post_id).toBe('p-known')
    expect(feed.byId('p-missing')).toBeUndefined()
  })

  it('parentIdOf: bevorzugt parent_comment_id vor parent_post_id', () => {
    expect(
      parentIdOf(mkPost({ parent_comment_id: 'c-1', parent_post_id: 'p-1' })),
    ).toBe('c-1')
  })

  it('parentIdOf: faellt auf parent_post_id zurueck, wenn parent_comment_id fehlt', () => {
    expect(parentIdOf(mkPost({ parent_comment_id: null, parent_post_id: 'p-1' }))).toBe('p-1')
  })

  it('parentIdOf: null, wenn beide Kanten fehlen (Strang-Wurzel)', () => {
    expect(parentIdOf(mkPost({ parent_comment_id: null, parent_post_id: null }))).toBeNull()
  })

  // Slice UI-2b (#1713) — buildThreadSummaries, collectThreadNodes (§2.7, §2.8)

  describe('buildThreadSummaries', () => {
    it('gruppiert Replies/Reposts/Quotes unter ihre Wurzel und zaehlt korrekt', () => {
      const posts = [
        mkPost({ post_id: 'root-1', kind: 'post', parent_post_id: null, round_num: 0 }),
        mkPost({
          post_id: 'reply-1',
          kind: 'comment',
          parent_post_id: 'root-1',
          root_post_id: 'root-1',
          round_num: 1,
          timestamp: '2026-05-15T12:01:00Z',
        }),
        mkPost({
          post_id: 'repost-1',
          kind: 'repost',
          parent_post_id: 'root-1',
          root_post_id: 'root-1',
          round_num: 1,
          timestamp: '2026-05-15T12:02:00Z',
        }),
        mkPost({
          post_id: 'quote-1',
          kind: 'quote',
          root_post_id: 'root-1',
          round_num: 2,
          timestamp: '2026-05-15T12:03:00Z',
        }),
      ]
      const summaries = buildThreadSummaries(posts)
      expect(summaries).toHaveLength(1)
      expect(summaries[0].root.post_id).toBe('root-1')
      expect(summaries[0].replyCount).toBe(1)
      expect(summaries[0].repostCount).toBe(1)
      expect(summaries[0].quoteCount).toBe(1)
      expect(summaries[0].activeRounds).toEqual([0, 1, 2])
      expect(summaries[0].lastActivityAt).toBe('2026-05-15T12:03:00Z')
    })

    it('kind=comment/quote/repost ohne Elternkante ist nie eine Wurzel (Data Gap)', () => {
      const orphanComment = mkPost({ post_id: 'c-1', kind: 'comment', parent_post_id: null })
      const summaries = buildThreadSummaries([orphanComment])
      expect(summaries).toHaveLength(0)
    })

    it('kind=null (Legacy-Daten) ohne Elternkante zaehlt als Wurzel', () => {
      const legacyRoot = mkPost({ post_id: 'legacy-1', kind: null, parent_post_id: null })
      const summaries = buildThreadSummaries([legacyRoot])
      expect(summaries).toHaveLength(1)
      expect(summaries[0].root.post_id).toBe('legacy-1')
    })

    it('loest die Wurzel ueber die Elternkette auf, wenn root_post_id fehlt', () => {
      const posts = [
        mkPost({ post_id: 'root-2', kind: 'post', parent_post_id: null }),
        mkPost({ post_id: 'reply-a', kind: 'comment', parent_post_id: 'root-2' }),
        mkPost({ post_id: 'reply-b', parent_comment_id: 'reply-a' }),
      ]
      const summaries = buildThreadSummaries(posts)
      expect(summaries).toHaveLength(1)
      expect(summaries[0].replyCount).toBe(2)
    })

    it('sortiert Straenge nach lastActivityAt absteigend', () => {
      const posts = [
        mkPost({ post_id: 'root-old', kind: 'post', timestamp: '2026-05-15T10:00:00Z' }),
        mkPost({ post_id: 'root-new', kind: 'post', timestamp: '2026-05-15T11:00:00Z' }),
      ]
      const summaries = buildThreadSummaries(posts)
      expect(summaries.map((s) => s.root.post_id)).toEqual(['root-new', 'root-old'])
    })

    it('ein Post mit unbekanntem root_post_id und ohne aufloesbare Kette gehoert zu keinem Strang', () => {
      const orphan = mkPost({ post_id: 'orphan-1', root_post_id: 'missing-root', parent_post_id: null, kind: 'comment' })
      const summaries = buildThreadSummaries([orphan])
      expect(summaries).toHaveLength(0)
    })
  })

  describe('collectThreadNodes', () => {
    it('sammelt alle Nachfahren einer Wurzel ueber root_post_id', () => {
      const posts = [
        mkPost({ post_id: 'root-3', kind: 'post' }),
        mkPost({ post_id: 'a', root_post_id: 'root-3', parent_post_id: 'root-3' }),
        mkPost({ post_id: 'b', root_post_id: 'root-3', parent_comment_id: 'a' }),
        mkPost({ post_id: 'other-root', kind: 'post' }),
      ]
      const nodes = collectThreadNodes('root-3', posts)
      expect(nodes.map((n) => n.post_id).sort()).toEqual(['a', 'b'])
    })

    it('sammelt Nachfahren ueber die Elternkette, wenn root_post_id fehlt', () => {
      const posts = [
        mkPost({ post_id: 'root-4', kind: 'post' }),
        mkPost({ post_id: 'child', parent_post_id: 'root-4' }),
        mkPost({ post_id: 'grandchild', parent_comment_id: 'child' }),
      ]
      const nodes = collectThreadNodes('root-4', posts)
      expect(nodes.map((n) => n.post_id).sort()).toEqual(['child', 'grandchild'])
    })

    it('liefert eine leere Liste ohne Nachfahren', () => {
      const posts = [mkPost({ post_id: 'lonely-root', kind: 'post' })]
      expect(collectThreadNodes('lonely-root', posts)).toEqual([])
    })
  })
})
