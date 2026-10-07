import { describe, expect, it } from 'vitest'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import {
  MAX_THREAD_DEPTH,
  buildRedditList,
  buildRedditTree,
  buildTwitterThread,
  buildTwitterTimeline,
  countUnrounded,
  effectiveKind,
  filterPosts,
  maxRoundOf,
  postsUpToRound,
} from '../threads'

let clock = 0
function mk(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  clock += 1
  const ts = new Date(Date.UTC(2026, 0, 1, 12, 0, clock)).toISOString()
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: `twitter:${clock}`,
    parent_post_id: null,
    platform: 'twitter',
    persona_id: '0',
    persona_name: 'Anna',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'text',
    timestamp: ts,
    score: 0,
    ...overrides,
  }
}

describe('effectiveKind', () => {
  it('nimmt ein gesetztes kind', () => {
    expect(effectiveKind(mk({ kind: 'quote' }))).toBe('quote')
  })
  it('leitet bei Altläufen ohne kind ab', () => {
    expect(effectiveKind(mk({ reposted_post_id: 'twitter:1' }))).toBe('repost')
    expect(effectiveKind(mk({ quoted_post_id: 'twitter:1' }))).toBe('quote')
    expect(effectiveKind(mk({ post_id: 'reddit:comment:3', platform: 'reddit' }))).toBe('comment')
    expect(effectiveKind(mk({ parent_post_id: 'twitter:1' }))).toBe('comment')
    expect(effectiveKind(mk())).toBe('post')
  })
})

describe('buildTwitterTimeline', () => {
  it('zählt Antworten, Reposts, Zitate und Likes am Originalbeitrag', () => {
    const root = mk({ post_id: 'twitter:1', like_count: 7 })
    const reply = mk({ post_id: 'twitter:2', parent_post_id: 'twitter:1', kind: 'comment' })
    const deep = mk({ post_id: 'twitter:3', parent_post_id: 'twitter:2', kind: 'comment' })
    const repost = mk({
      post_id: 'twitter:4',
      kind: 'repost',
      reposted_post_id: 'twitter:1',
      body: '',
    })
    const quote = mk({
      post_id: 'twitter:5',
      kind: 'quote',
      quoted_post_id: 'twitter:1',
      body: 'Dazu meine Sicht',
    })
    const entries = buildTwitterTimeline([quote, deep, repost, reply, root])

    expect(entries.map((e) => e.post.post_id)).toEqual(['twitter:1', 'twitter:5'])
    const first = entries[0]
    expect(first).toMatchObject({ replies: 2, reposts: 1, quotes: 1, likes: 7 })
    // Zitat: eigener Beitrag mit Verweis auf das Original.
    expect(entries[1]).toMatchObject({
      kind: 'quote',
      quotedPostId: 'twitter:1',
      referenceMissing: false,
    })
    expect(entries[1].quotedPost?.post_id).toBe('twitter:1')
  })

  it('zeigt einen Repost ohne Original als eigenen Eintrag mit referenceMissing', () => {
    const repost = mk({ kind: 'repost', reposted_post_id: 'twitter:gone', body: '' })
    const [entry] = buildTwitterTimeline([repost])
    expect(entry.kind).toBe('repost')
    expect(entry.referenceMissing).toBe(true)
  })

  it('meldet ein Zitat mit fehlendem Original', () => {
    const quote = mk({ kind: 'quote', quoted_post_id: 'twitter:gone' })
    expect(buildTwitterTimeline([quote])[0].referenceMissing).toBe(true)
  })

  it('Altlauf ohne kind: Antworten über parent_post_id, Reposts über reposted_post_id', () => {
    const root = mk({ post_id: 'twitter:1' })
    const reply = mk({ post_id: 'twitter:2', parent_post_id: 'twitter:1' })
    const repost = mk({ post_id: 'twitter:3', reposted_post_id: 'twitter:1', body: '' })
    const [entry] = buildTwitterTimeline([root, reply, repost])
    expect(entry).toMatchObject({ replies: 1, reposts: 1 })
  })

  it('ignoriert Reddit, sortiert chronologisch, verändert die Eingabe nicht', () => {
    const late = mk({ post_id: 'twitter:late' })
    const early = { ...mk({ post_id: 'twitter:early' }), timestamp: '2025-01-01T00:00:00Z' }
    const reddit = mk({ platform: 'reddit', post_id: 'reddit:1' })
    const input = [late, reddit, early]
    const result = buildTwitterTimeline(input)
    expect(result.map((e) => e.post.post_id)).toEqual(['twitter:early', 'twitter:late'])
    expect(input[0]).toBe(late)
  })

  it('zählt Antworten im Kreis nicht', () => {
    const root = mk({ post_id: 'twitter:1' })
    const a = mk({ post_id: 'twitter:a', parent_post_id: 'twitter:b', kind: 'comment' })
    const b = mk({ post_id: 'twitter:b', parent_post_id: 'twitter:a', kind: 'comment' })
    const [entry] = buildTwitterTimeline([root, a, b])
    expect(entry.replies).toBe(0)
  })
})

describe('buildTwitterThread', () => {
  const root = mk({ post_id: 'twitter:1' })
  const a = mk({ post_id: 'twitter:2', parent_post_id: 'twitter:1', kind: 'comment' })
  const b = mk({ post_id: 'twitter:3', parent_post_id: 'twitter:2', kind: 'comment' })
  const c = mk({ post_id: 'twitter:4', parent_post_id: 'twitter:1', kind: 'comment' })

  it('liefert Wurzel und Antworten mit Tiefe in Anzeigereihenfolge', () => {
    const thread = buildTwitterThread('twitter:1', [c, b, a, root])
    expect(thread.rootMissing).toBe(false)
    expect(thread.root?.post_id).toBe('twitter:1')
    expect(thread.nodes.map((n) => [n.post.post_id, n.depth])).toEqual([
      ['twitter:2', 1],
      ['twitter:3', 2],
      ['twitter:4', 1],
    ])
    expect(thread.nodes.map((n) => n.isLastChild)).toEqual([false, true, true])
    expect(thread.nodes[1].parentId).toBe('twitter:2')
  })

  it('löst eine Antwort zur Wurzel auf', () => {
    const thread = buildTwitterThread('twitter:3', [root, a, b, c])
    expect(thread.rootId).toBe('twitter:1')
    expect(thread.nodes).toHaveLength(3)
  })

  it('meldet rootMissing, wenn die Wurzel nicht im Bestand ist', () => {
    const orphanA = mk({ post_id: 'twitter:2', parent_post_id: 'twitter:gone', kind: 'comment' })
    const orphanB = mk({ post_id: 'twitter:3', parent_post_id: 'twitter:2', kind: 'comment' })
    const fromReply = buildTwitterThread('twitter:3', [orphanA, orphanB])
    expect(fromReply.rootMissing).toBe(true)
    expect(fromReply.root).toBeNull()
    expect(fromReply.rootId).toBe('twitter:gone')
    expect(fromReply.nodes.map((n) => n.post.post_id)).toEqual(['twitter:2', 'twitter:3'])
    // Die fehlende Wurzel direkt anzufragen führt zum selben Faden.
    const direct = buildTwitterThread('twitter:gone', [orphanA, orphanB])
    expect(direct.rootMissing).toBe(true)
    expect(direct.nodes).toHaveLength(2)
  })

  it('nimmt root_post_id, wenn die Kette an einem unbekannten Zwischenglied abreißt', () => {
    const reply = mk({
      post_id: 'twitter:2',
      parent_post_id: 'twitter:missing-mid',
      root_post_id: 'twitter:1',
      kind: 'comment',
    })
    const thread = buildTwitterThread('twitter:2', [root, reply])
    expect(thread.rootId).toBe('twitter:1')
    expect(thread.nodes[0]).toMatchObject({ depth: 1, parentMissing: true })
  })

  it('bricht bei einem Zyklus ab, statt zu hängen', () => {
    const x = mk({ post_id: 'twitter:x', parent_post_id: 'twitter:y', kind: 'comment' })
    const y = mk({ post_id: 'twitter:y', parent_post_id: 'twitter:x', kind: 'comment' })
    const thread = buildTwitterThread('twitter:x', [x, y])
    expect(thread.broken).toBe(true)
    expect(thread.root).toBeNull()
    expect(thread.nodes).toEqual([])
  })

  it('führt Zitate und Reposts getrennt von den Antworten', () => {
    const repost = mk({ post_id: 'twitter:9', kind: 'repost', reposted_post_id: 'twitter:1', body: '' })
    const quote = mk({ post_id: 'twitter:10', kind: 'quote', quoted_post_id: 'twitter:1' })
    const thread = buildTwitterThread('twitter:1', [root, a, repost, quote])
    expect(thread.reposts).toBe(1)
    expect(thread.quotes.map((q) => q.post_id)).toEqual(['twitter:10'])
    expect(thread.nodes.map((n) => n.post.post_id)).toEqual(['twitter:2'])
  })

  it('ein Altlauf-Repost löst zum Faden des Originals auf', () => {
    const repost = mk({ post_id: 'twitter:9', reposted_post_id: 'twitter:1', root_post_id: 'twitter:1', body: '' })
    expect(buildTwitterThread('twitter:9', [root, a, repost]).rootId).toBe('twitter:1')
  })

  it('kappt zu tiefe Fäden', () => {
    const chain: PostCreatedEvent[] = [root]
    for (let i = 0; i < MAX_THREAD_DEPTH + 5; i++) {
      chain.push(
        mk({
          post_id: `twitter:d${i}`,
          parent_post_id: i === 0 ? 'twitter:1' : `twitter:d${i - 1}`,
          root_post_id: 'twitter:1',
          kind: 'comment',
        }),
      )
    }
    const thread = buildTwitterThread('twitter:1', chain)
    expect(Math.max(...thread.nodes.map((n) => n.depth))).toBeLessThanOrEqual(MAX_THREAD_DEPTH)
  })
})

describe('Reddit', () => {
  const post = mk({ platform: 'reddit', post_id: 'reddit:1', kind: 'post', score: 4 })
  const c1 = mk({
    platform: 'reddit',
    post_id: 'reddit:comment:1',
    parent_post_id: 'reddit:1',
    root_post_id: 'reddit:1',
    kind: 'comment',
  })

  it('buildRedditList: Score und Kommentarzahl, ohne Kommentare und Twitter', () => {
    const c2 = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:2',
      parent_post_id: 'reddit:comment:1',
      parent_comment_id: 'reddit:comment:1',
      kind: 'comment',
    })
    const tw = mk()
    const list = buildRedditList([c2, c1, post, tw])
    expect(list).toHaveLength(1)
    expect(list[0]).toMatchObject({ score: 4, commentCount: 2 })
  })

  it('buildRedditTree verschachtelt über parent_comment_id', () => {
    const c2 = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:2',
      parent_post_id: 'reddit:1',
      parent_comment_id: 'reddit:comment:1',
      kind: 'comment',
    })
    const c3 = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:3',
      parent_post_id: 'reddit:1',
      kind: 'comment',
    })
    const result = buildRedditTree('reddit:1', [post, c1, c2, c3])
    expect(result.flatOnly).toBe(false)
    expect(result.commentCount).toBe(3)
    expect(result.tree.map((n) => n.post.post_id)).toEqual(['reddit:comment:1', 'reddit:comment:3'])
    expect(result.tree[0].children.map((n) => [n.post.post_id, n.depth])).toEqual([
      ['reddit:comment:2', 2],
    ])
    expect(result.unplacedCount).toBe(0)
  })

  it('flatOnly bei Altlauf ohne parent_comment_id: Kommentare flach unter dem Beitrag', () => {
    const c2 = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:2',
      parent_post_id: 'reddit:1',
      kind: 'comment',
    })
    const result = buildRedditTree('reddit:1', [post, c1, c2])
    expect(result.flatOnly).toBe(true)
    expect(result.tree).toHaveLength(2)
    expect(result.tree.every((n) => n.children.length === 0)).toBe(true)
  })

  it('flatOnly ist falsch ohne Kommentare', () => {
    expect(buildRedditTree('reddit:1', [post]).flatOnly).toBe(false)
  })

  it('Altlauf ohne kind: Kommentar am post_id-Muster erkannt', () => {
    const legacyComment = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:7',
      parent_post_id: 'reddit:1',
    })
    const result = buildRedditTree('reddit:1', [{ ...post, kind: undefined }, legacyComment])
    expect(result.commentCount).toBe(1)
    expect(buildRedditList([{ ...post, kind: undefined }, legacyComment])[0].commentCount).toBe(1)
  })

  it('Zyklus zwischen Kommentaren: nicht im Baum, kein Hängen', () => {
    const x = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:x',
      parent_comment_id: 'reddit:comment:y',
      kind: 'comment',
    })
    const y = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:y',
      parent_comment_id: 'reddit:comment:x',
      kind: 'comment',
    })
    const result = buildRedditTree('reddit:1', [post, c1, x, y])
    expect(result.tree.map((n) => n.post.post_id)).toEqual(['reddit:comment:1'])
  })

  it('fehlender Elternkommentar: Knoten hängt am Beitrag, parentMissing', () => {
    const orphan = mk({
      platform: 'reddit',
      post_id: 'reddit:comment:9',
      parent_post_id: 'reddit:1',
      parent_comment_id: 'reddit:comment:gone',
      root_post_id: 'reddit:1',
      kind: 'comment',
    })
    const result = buildRedditTree('reddit:1', [post, orphan])
    expect(result.tree[0]).toMatchObject({ depth: 1, parentMissing: true })
  })

  it('fehlender Beitrag: rootMissing, Kommentare bleiben über root_post_id erreichbar', () => {
    const result = buildRedditTree('reddit:1', [c1])
    expect(result.rootMissing).toBe(true)
    expect(result.commentCount).toBe(1)
  })

  it('Tiefenschutz zählt Überhang als unplatziert', () => {
    const chain: PostCreatedEvent[] = [post]
    for (let i = 0; i < MAX_THREAD_DEPTH + 3; i++) {
      chain.push(
        mk({
          platform: 'reddit',
          post_id: `reddit:comment:d${i}`,
          parent_post_id: 'reddit:1',
          parent_comment_id: i === 0 ? null : `reddit:comment:d${i - 1}`,
          root_post_id: 'reddit:1',
          kind: 'comment',
        }),
      )
    }
    const result = buildRedditTree('reddit:1', chain)
    // Kette länger als der Schutz: der Überhang wird gezählt, nicht gerendert.
    expect(result.commentCount).toBe(MAX_THREAD_DEPTH + 3)
    expect(result.unplacedCount).toBeGreaterThan(0)
  })
})

describe('Filter und Rundenschnitt', () => {
  const p0 = mk({ post_id: 'twitter:1', round_num: 1, persona_id: '0', body: 'Wärmepumpe lohnt sich' })
  const p1 = mk({ post_id: 'reddit:1', platform: 'reddit', round_num: 2, persona_id: '1', persona_name: 'Berta' })
  const p2 = mk({ post_id: 'twitter:2', round_num: 3, persona_id: '0', quote_body: 'Gas bleibt' })
  const none = mk({ post_id: 'twitter:3', persona_id: '2' })
  const all = [p0, p1, p2, none]

  it('filtert nach Netzwerk, Persona, Runde und Freitext', () => {
    expect(filterPosts(all, { network: 'reddit' })).toEqual([p1])
    expect(filterPosts(all, { network: 'all' })).toHaveLength(4)
    expect(filterPosts(all, { personaId: '0' })).toEqual([p0, p2])
    expect(filterPosts(all, { round: 2 })).toEqual([p1])
    expect(filterPosts(all, { query: '  WÄRMEPUMPE ' })).toEqual([p0])
    expect(filterPosts(all, { query: 'gas' })).toEqual([p2])
    expect(filterPosts(all, { query: 'berta' })).toEqual([p1])
    expect(filterPosts(all, { network: 'twitter', personaId: '0', round: 3 })).toEqual([p2])
    expect(filterPosts(all, {})).toHaveLength(4)
  })

  it('exakte Runde schließt Beiträge ohne round_num aus', () => {
    expect(filterPosts(all, { round: 1 })).not.toContain(none)
  })

  it('postsUpToRound schneidet kumulativ und behält Beiträge ohne round_num', () => {
    expect(postsUpToRound(all, 2)).toEqual([p0, p1, none])
    expect(postsUpToRound(all, null)).toEqual(all)
    expect(countUnrounded(all)).toBe(1)
    expect(maxRoundOf(all)).toBe(3)
    expect(maxRoundOf([none])).toBeNull()
  })
})
