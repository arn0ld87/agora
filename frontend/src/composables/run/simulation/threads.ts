/**
 * Reine Funktionen für Feed und Faden des Laufs (Etappe 4, #1801).
 *
 * Eingabe sind immer Listen von `PostCreatedEvent` (Snapshot und Live-Strom
 * gemischt). Keine Funktion verändert ihre Eingabe, keine greift auf Store oder
 * Netz zu. Reihenfolge überall: chronologisch aufsteigend (älteste zuerst);
 * die Oberfläche dreht bei Bedarf um.
 *
 * Datenlage, die hier ausdrücklich behandelt wird:
 * - Altläufe tragen kein `kind`: es wird aus `reposted_post_id`,
 *   `quoted_post_id`, dem `:comment:`-Muster der `post_id` und der Elternkante
 *   abgeleitet (`effectiveKind`).
 * - Der Snapshot liefert weder `round_num` noch `parent_comment_id` und für
 *   Twitter keine `parent_post_id` (backend/app/api/simulation_history.py).
 *   Fehlende Wurzeln und flache Kommentarlisten sind darum ein erwartbarer
 *   Zustand und werden als Kennzeichen (`rootMissing`, `flatOnly`) gemeldet,
 *   nicht still geglättet.
 * - Zyklen und überlange Ketten brechen die Zuordnung ab, statt zu hängen.
 *
 * Wiederverwendet aus `useSimFeed`: `parentIdOf`, `isThreadRoot`.
 */
import type { PostCreatedEvent, PostKind } from '@/contracts/postEventContract'
import { isThreadRoot as hasNoParentAndPostKind, parentIdOf } from '@/composables/useSimFeed'

export type FeedPost = PostCreatedEvent
export type FeedNetwork = 'twitter' | 'reddit'

/** Maximale Länge einer Elternkette bzw. Tiefe eines Baums. */
export const MAX_THREAD_DEPTH = 32

// --- gemeinsame Helfer --------------------------------------------------

/**
 * Art eines Beitrags. Ein gesetztes `kind` gilt; sonst Ableitung für Altläufe:
 * `reposted_post_id` → repost, `quoted_post_id` → quote, `:comment:`-`post_id`
 * oder Elternkante → comment, sonst post.
 */
export function effectiveKind(post: FeedPost): PostKind {
  if (post.kind) return post.kind
  if (post.reposted_post_id) return 'repost'
  if (post.quoted_post_id) return 'quote'
  if (post.post_id.includes(':comment:') || parentIdOf(post) !== null) return 'comment'
  return 'post'
}

function timeOf(post: FeedPost): number {
  const t = Date.parse(post.timestamp)
  return Number.isNaN(t) ? 0 : t
}

/** Stabil chronologisch aufsteigend sortierte Kopie. */
function sortChrono(posts: readonly FeedPost[]): FeedPost[] {
  return posts
    .map((post, index) => ({ post, index }))
    .sort((a, b) => timeOf(a.post) - timeOf(b.post) || a.index - b.index)
    .map((entry) => entry.post)
}

function indexById(posts: readonly FeedPost[]): Map<string, FeedPost> {
  const byId = new Map<string, FeedPost>()
  for (const p of posts) byId.set(p.post_id, p)
  return byId
}

interface GroupKey {
  /** post_id der (vermuteten) Strang-Wurzel; kann im Bestand fehlen. */
  key: string
  /** Die Elternkette läuft im Kreis oder ist länger als MAX_THREAD_DEPTH. */
  broken: boolean
}

/**
 * Strang-Schlüssel eines Beitrags. Läuft die Elternkette bis zu einem Beitrag
 * ohne Eltern, ist dieser die Wurzel. Bricht sie an einem unbekannten Vorfahren
 * ab, gilt `root_post_id`, sonst die Kennung des unbekannten Vorfahren — so
 * bleiben Antworten auf eine fehlende Wurzel gruppierbar. Zyklen und
 * Überlänge: `broken`, der Beitrag bekommt sich selbst als Schlüssel.
 */
function groupKeyOf(post: FeedPost, byId: Map<string, FeedPost>): GroupKey {
  const visited = new Set<string>()
  let current: FeedPost = post
  for (let i = 0; i < MAX_THREAD_DEPTH; i++) {
    if (visited.has(current.post_id)) return { key: post.post_id, broken: true }
    visited.add(current.post_id)
    const parentId = parentIdOf(current)
    if (parentId === null) {
      // Wurzel gefunden, außer ein Kommentar/Zitat ohne Elternkante (Datenlücke).
      if (isThreadRoot(current) || effectiveKind(current) === 'quote') {
        return { key: current.post_id, broken: false }
      }
      return { key: post.root_post_id ?? current.post_id, broken: false }
    }
    const parent = byId.get(parentId)
    if (!parent) return { key: post.root_post_id ?? parentId, broken: false }
    current = parent
  }
  // Kette länger als der Schutz (kein Zyklus): root_post_id trägt die Zuordnung,
  // die Tiefe kappt später der Baum.
  if (post.root_post_id) return { key: post.root_post_id, broken: false }
  return { key: post.post_id, broken: true }
}

/**
 * Wurzelbeitrag: `isThreadRoot` aus `useSimFeed` (keine Elternkante, kind post
 * oder unbekannt), aber ohne Altlauf-Reposts/-Zitate, die kein `kind` tragen.
 */
function isThreadRoot(post: FeedPost): boolean {
  return hasNoParentAndPostKind(post) && effectiveKind(post) === 'post'
}

function isQuote(post: FeedPost): boolean {
  return effectiveKind(post) === 'quote'
}

/** Wurzel-artig für die Twitter-Zeitleiste: Wurzelbeitrag oder Zitat. */
function isTimelineEntry(post: FeedPost): boolean {
  return isThreadRoot(post) || isQuote(post)
}

// --- Twitter ------------------------------------------------------------

export interface TimelineEntry {
  post: FeedPost
  kind: PostKind
  /** Antworten im ganzen Strang (alle Tiefen), ohne Reposts und Zitate. */
  replies: number
  /** Reposts dieses Beitrags (`reposted_post_id`). */
  reposts: number
  /** Zitate dieses Beitrags (`quoted_post_id`). */
  quotes: number
  /** `like_count` des Beitrags selbst (0 bei Altdaten ohne Wert). */
  likes: number
  /** Bei Zitaten: Kennung des zitierten Beitrags, sonst null. */
  quotedPostId: string | null
  /** Bei Zitaten: der zitierte Beitrag, wenn im Bestand. */
  quotedPost: FeedPost | null
  /**
   * Bezug (Original eines Reposts bzw. Zitats) steht nicht im Bestand. Reposts
   * ohne Original bleiben als eigener Eintrag sichtbar, statt zu verschwinden.
   */
  referenceMissing: boolean
}

/**
 * Twitter-Zeitleiste: Wurzelbeiträge und Zitate chronologisch, je mit Zählern.
 * Ein Repost ist kein eigener Eintrag, sondern erhöht `reposts` des Originals;
 * fehlt das Original, erscheint der Repost selbst mit `referenceMissing`.
 * Ein Zitat ist ein eigener Eintrag mit Verweis und zählt zugleich in `quotes`
 * des Originals. Antworten zählen zum Strang-Eintrag, unter dem sie hängen.
 * Reddit-Beiträge werden ignoriert.
 */
export function buildTwitterTimeline(posts: readonly FeedPost[]): TimelineEntry[] {
  const twitter = posts.filter((p) => p.platform === 'twitter')
  const byId = indexById(twitter)

  const reposts = new Map<string, number>()
  const quotes = new Map<string, number>()
  const replies = new Map<string, number>()
  for (const p of twitter) {
    const kind = effectiveKind(p)
    if (kind === 'repost') {
      const target = p.reposted_post_id ?? p.root_post_id
      if (target) reposts.set(target, (reposts.get(target) ?? 0) + 1)
    } else if (kind === 'quote') {
      if (p.quoted_post_id) quotes.set(p.quoted_post_id, (quotes.get(p.quoted_post_id) ?? 0) + 1)
    }
    if (kind === 'comment' || (kind === 'post' && !isThreadRoot(p))) {
      const { key, broken } = groupKeyOf(p, byId)
      if (!broken) replies.set(key, (replies.get(key) ?? 0) + 1)
    }
  }

  const entries: TimelineEntry[] = []
  for (const p of sortChrono(twitter)) {
    const kind = effectiveKind(p)
    if (isTimelineEntry(p)) {
      const quotedId = kind === 'quote' ? (p.quoted_post_id ?? null) : null
      const quotedPost = quotedId ? (byId.get(quotedId) ?? null) : null
      entries.push({
        post: p,
        kind,
        replies: replies.get(p.post_id) ?? 0,
        reposts: reposts.get(p.post_id) ?? 0,
        quotes: quotes.get(p.post_id) ?? 0,
        likes: p.like_count ?? 0,
        quotedPostId: quotedId,
        quotedPost,
        referenceMissing: kind === 'quote' && quotedPost === null,
      })
    } else if (kind === 'repost') {
      const target = p.reposted_post_id ?? p.root_post_id
      if (!target || !byId.has(target)) {
        entries.push({
          post: p,
          kind,
          replies: 0,
          reposts: 0,
          quotes: 0,
          likes: p.like_count ?? 0,
          quotedPostId: null,
          quotedPost: null,
          referenceMissing: true,
        })
      }
    }
  }
  return entries
}

export interface ThreadNode {
  post: FeedPost
  /** 1 = direkte Antwort auf die Wurzel; wächst mit jeder Ebene. */
  depth: number
  /** Eltern-Kennung (die Wurzel oder eine andere Antwort). */
  parentId: string
  /** Elternbeitrag steht nicht im Bestand; der Knoten hängt dann an der Wurzel. */
  parentMissing: boolean
  /** Letzte Antwort unter ihrem Eltern-Knoten (für das Ende der Verbindungslinie). */
  isLastChild: boolean
}

export interface ThreadResult {
  /** Kennung der (vermuteten) Wurzel; auch bei fehlender Wurzel gesetzt. */
  rootId: string
  /** Wurzelbeitrag oder null, wenn er nicht im Bestand ist. */
  root: FeedPost | null
  /** Wurzel nicht im Bestand (typisch: Puffer- oder Snapshot-Grenze). */
  rootMissing: boolean
  /** Die Elternkette der angefragten Kennung läuft im Kreis oder ist zu lang. */
  broken: boolean
  /** Antworten in Anzeigereihenfolge (Tiefensuche, je Ebene chronologisch). */
  nodes: ThreadNode[]
  /** Zitate der Wurzel (eigene Beiträge mit Verweis). */
  quotes: FeedPost[]
  /** Anzahl Reposts der Wurzel. */
  reposts: number
}

/**
 * Faden zu einer Kennung. Ist sie eine Antwort, wird zur Wurzel aufgelöst; ist
 * sie unbekannt, gilt sie selbst als fehlende Wurzel und gesammelt werden die
 * Antworten, die auf sie zeigen. Reposts und Zitate stehen nicht in `nodes`.
 */
export function buildTwitterThread(
  rootOrAnyId: string,
  posts: readonly FeedPost[],
): ThreadResult {
  const twitter = posts.filter((p) => p.platform === 'twitter')
  const byId = indexById(twitter)

  const start = byId.get(rootOrAnyId)
  let rootId = rootOrAnyId
  if (start && !isTimelineEntry(start)) {
    const group = groupKeyOf(start, byId)
    if (group.broken) {
      return {
        rootId: start.post_id,
        root: null,
        rootMissing: true,
        broken: true,
        nodes: [],
        quotes: [],
        reposts: 0,
      }
    }
    rootId = group.key
  }

  const root = byId.get(rootId) ?? null
  const members: FeedPost[] = []
  const quoteList: FeedPost[] = []
  let repostCount = 0
  for (const p of twitter) {
    if (p.post_id === rootId) continue
    const kind = effectiveKind(p)
    if (kind === 'repost') {
      if ((p.reposted_post_id ?? p.root_post_id) === rootId) repostCount += 1
      continue
    }
    if (kind === 'quote') {
      if (p.quoted_post_id === rootId) quoteList.push(p)
      continue
    }
    if (isThreadRoot(p)) continue
    const group = groupKeyOf(p, byId)
    if (!group.broken && group.key === rootId) members.push(p)
  }

  const memberIds = new Set(members.map((p) => p.post_id))
  const childrenOf = new Map<string, FeedPost[]>()
  const missingParent = new Set<string>()
  for (const p of sortChrono(members)) {
    const parentId = parentIdOf(p)
    let attachTo = rootId
    if (parentId !== null && memberIds.has(parentId)) {
      attachTo = parentId
    } else if (parentId !== null && parentId !== rootId) {
      missingParent.add(p.post_id)
    }
    const list = childrenOf.get(attachTo) ?? []
    list.push(p)
    childrenOf.set(attachTo, list)
  }

  const nodes: ThreadNode[] = []
  const visit = (parentId: string, depth: number): void => {
    if (depth > MAX_THREAD_DEPTH) return
    const children = childrenOf.get(parentId) ?? []
    children.forEach((child, i) => {
      nodes.push({
        post: child,
        depth,
        parentId,
        parentMissing: missingParent.has(child.post_id),
        isLastChild: i === children.length - 1,
      })
      visit(child.post_id, depth + 1)
    })
  }
  visit(rootId, 1)

  return {
    rootId,
    root,
    rootMissing: root === null,
    broken: false,
    nodes,
    quotes: sortChrono(quoteList),
    reposts: repostCount,
  }
}

// --- Reddit -------------------------------------------------------------

export interface RedditListEntry {
  post: FeedPost
  /** Voting-Stand (`score`). */
  score: number
  /** Kommentare im ganzen Strang, alle Tiefen. */
  commentCount: number
}

function isRedditComment(post: FeedPost): boolean {
  return effectiveKind(post) === 'comment'
}

/**
 * Reddit-Beitragsliste: Beiträge (keine Kommentare), chronologisch aufsteigend,
 * mit Stimmenstand und Kommentarzahl. Twitter-Beiträge werden ignoriert.
 */
export function buildRedditList(posts: readonly FeedPost[]): RedditListEntry[] {
  const reddit = posts.filter((p) => p.platform === 'reddit')
  const byId = indexById(reddit)
  const counts = new Map<string, number>()
  for (const p of reddit) {
    if (!isRedditComment(p)) continue
    const { key, broken } = groupKeyOf(p, byId)
    if (!broken) counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return sortChrono(reddit.filter((p) => !isRedditComment(p))).map((post) => ({
    post,
    score: post.score,
    commentCount: counts.get(post.post_id) ?? 0,
  }))
}

export interface RedditNode {
  post: FeedPost
  /** 1 = Kommentar direkt unter dem Beitrag. */
  depth: number
  children: RedditNode[]
  /** Elternkommentar steht nicht im Bestand; der Knoten hängt am Beitrag. */
  parentMissing: boolean
}

export interface RedditTreeResult {
  rootId: string
  /** Beitrag oder null, wenn er nicht im Bestand ist. */
  root: FeedPost | null
  rootMissing: boolean
  /** Kommentare direkt unter dem Beitrag, verschachtelt. */
  tree: RedditNode[]
  /** Kommentare des Strangs insgesamt (platziert und unplatziert). */
  commentCount: number
  /**
   * Kein Kommentar im übergebenen Bestand trägt `parent_comment_id`, obwohl
   * Kommentare existieren: Altlauf oder Snapshot ohne Verschachtelung. Die
   * Oberfläche zeigt dann einen Datenlücken-Hinweis; die Kommentare stehen
   * flach unter dem Beitrag.
   */
  flatOnly: boolean
  /** Kommentare, die wegen Zyklus oder Tiefenschutz nicht im Baum stehen. */
  unplacedCount: number
}

/** True, wenn Kommentare existieren, aber keiner ein `parent_comment_id` trägt. */
export function isFlatOnly(posts: readonly FeedPost[]): boolean {
  let comments = 0
  for (const p of posts) {
    if (p.platform !== 'reddit' || !isRedditComment(p)) continue
    comments += 1
    if (p.parent_comment_id) return false
  }
  return comments > 0
}

/**
 * Verschachtelter Kommentarbaum eines Reddit-Beitrags. Kante: `parent_comment_id`,
 * sonst `parent_post_id`. Kommentare je Ebene chronologisch. Zyklen und Tiefe
 * über `MAX_THREAD_DEPTH` werden nicht gerendert, sondern in `unplacedCount`
 * gezählt.
 */
export function buildRedditTree(
  postId: string,
  posts: readonly FeedPost[],
): RedditTreeResult {
  const reddit = posts.filter((p) => p.platform === 'reddit')
  const byId = indexById(reddit)
  const root = byId.get(postId) ?? null

  const members: FeedPost[] = []
  for (const p of reddit) {
    if (p.post_id === postId || !isRedditComment(p)) continue
    const group = groupKeyOf(p, byId)
    if (!group.broken && group.key === postId) members.push(p)
  }

  const memberIds = new Set(members.map((p) => p.post_id))
  const childrenOf = new Map<string, FeedPost[]>()
  const missingParent = new Set<string>()
  for (const p of sortChrono(members)) {
    const parentId = parentIdOf(p)
    let attachTo = postId
    if (parentId !== null && memberIds.has(parentId)) {
      attachTo = parentId
    } else if (parentId !== null && parentId !== postId) {
      missingParent.add(p.post_id)
    }
    const list = childrenOf.get(attachTo) ?? []
    list.push(p)
    childrenOf.set(attachTo, list)
  }

  let placed = 0
  const build = (parentId: string, depth: number): RedditNode[] => {
    if (depth > MAX_THREAD_DEPTH) return []
    return (childrenOf.get(parentId) ?? []).map((post) => {
      placed += 1
      return {
        post,
        depth,
        children: build(post.post_id, depth + 1),
        parentMissing: missingParent.has(post.post_id),
      }
    })
  }
  // Zyklen sind hier ausgeschlossen: ein Kommentar im Kreis hat keinen Weg zum
  // Beitrag und taucht in `members` nicht auf; Tiefenschutz deckt den Rest.
  const tree = build(postId, 1)

  return {
    rootId: postId,
    root,
    rootMissing: root === null,
    tree,
    commentCount: members.length,
    flatOnly: isFlatOnly(posts),
    unplacedCount: members.length - placed,
  }
}

// --- Filter und Rundenschnitt -------------------------------------------

export interface PostFilter {
  /** Netzwerk; fehlt oder `'all'` = beide. */
  network?: FeedNetwork | 'all' | null
  personaId?: string | null
  /** Genau diese Runde. Beiträge ohne `round_num` fallen heraus. */
  round?: number | null
  /** Freitext, ohne Groß-/Kleinschreibung, über Text, Zitattext und Name. */
  query?: string | null
}

/**
 * Filtert Beiträge nach Netzwerk, Persona, genau einer Runde und Freitext. Ein
 * nicht gesetzter Teil filtert nicht. Beiträge ohne `round_num` (Snapshot,
 * Altläufe) passen auf keine bestimmte Runde und fallen bei gesetztem `round`
 * heraus; für den Rundenschnitt siehe `postsUpToRound`.
 */
export function filterPosts(
  posts: readonly FeedPost[],
  filter: PostFilter,
): FeedPost[] {
  const query = filter.query?.trim().toLowerCase() ?? ''
  const network = filter.network && filter.network !== 'all' ? filter.network : null
  const round = filter.round ?? null
  const personaId = filter.personaId || null
  return posts.filter((p) => {
    if (network && p.platform !== network) return false
    if (personaId && p.persona_id !== personaId) return false
    if (round !== null && p.round_num !== round) return false
    if (query) {
      const haystack = `${p.body}\n${p.quote_body ?? ''}\n${p.persona_name}`.toLowerCase()
      if (!haystack.includes(query)) return false
    }
    return true
  })
}

/**
 * Rundenschnitt für „zurückgehen": Beiträge bis einschließlich `round`.
 * Beiträge ohne `round_num` lassen sich keiner Runde zuordnen. Sie bleiben
 * sichtbar (sie zu verbergen leerte den Feed für jeden Snapshot-Bestand) und
 * werden über `countUnrounded` ausgewiesen, damit die Oberfläche den
 * Datenlücken-Hinweis zeigen kann. `round = null` liefert alles.
 */
export function postsUpToRound(
  posts: readonly FeedPost[],
  round: number | null,
): FeedPost[] {
  if (round === null) return [...posts]
  return posts.filter((p) => p.round_num == null || p.round_num <= round)
}

/** Anzahl Beiträge ohne `round_num` (nicht auf eine Runde schneidbar). */
export function countUnrounded(posts: readonly FeedPost[]): number {
  let n = 0
  for (const p of posts) if (p.round_num == null) n += 1
  return n
}

/** Höchste vorkommende Runde oder null, wenn kein Beitrag eine trägt. */
export function maxRoundOf(posts: readonly FeedPost[]): number | null {
  let max: number | null = null
  for (const p of posts) {
    if (typeof p.round_num === 'number' && (max === null || p.round_num > max)) max = p.round_num
  }
  return max
}
