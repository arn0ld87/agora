/**
 * useSimFeed — State pro Simulation: Reddit-Thread + Twitter-Flow.
 *
 * Slice FE-Redesign-5 · 2026-05-15
 * Slice 9 · 2026-08-02 — Ringpuffer (MAX_POSTS_PER_FEED) + rAF-Batching (#1007)
 *
 * Konsumiert PostCreatedEvent (Slice 5-pre), routet nach platform,
 * dedupliziert per post_id, baut Reddit-Reply-Tree, sortiert Twitter
 * nach timestamp DESC.
 *
 * Eingehende Posts werden gepuffert und einmal pro Animation Frame
 * gebündelt in `all.value` geschrieben, um teure Neuberechnungen von
 * `twitterPosts`/`redditTree` nicht pro Event auszulösen. Dedup (`seen`)
 * und der simulation_id-Filter greifen weiterhin sofort in ingest()/
 * ingestMany(). `flushPending()` leert den Puffer synchron — für Tests,
 * die nicht auf einen Frame warten wollen.
 *
 * Singleton-Map pro simulationId — reset via clearSimFeed(simulationId).
 * LRU-Limit: max. 10 Einträge; ältester wird beim 11. evicted.
 */

import { computed, ref } from 'vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

export interface RedditNode extends PostCreatedEvent {
  children: RedditNode[]
}

/**
 * Kante-Regel fuer Straenge (Slice UI-2b, §2.8): `parent_comment_id`, wenn
 * gesetzt (Reddit-Baum), sonst `parent_post_id` (Twitter-Replies, flach, und
 * Reddit-Wurzelantworten vor dem Slice-5-Backfill). Funktioniert mit und
 * ohne `parent_comment_id` im Snapshot.
 */
export function parentIdOf(post: PostCreatedEvent): string | null {
  return post.parent_comment_id ?? post.parent_post_id ?? null
}

const MAX_STORES = 10

/**
 * Obergrenze der pro Feed gehaltenen Posts (Ringpuffer).
 * Ab hier wird das Rendern der TransitionGroup spürbar (Layout-Thrashing,
 * lange Reflow-Zeiten); 500 deckt beobachtete Lastspitzen einer Simulation
 * ab, ohne dass ältere Posts für die laufende Analyse noch relevant sind.
 */
export const MAX_POSTS_PER_FEED = 500

const stores = new Map<string, ReturnType<typeof createStore>>()

function scheduleFrame(fn: () => void): void {
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(fn)
  } else {
    setTimeout(fn, 16)
  }
}

function createStore(simulationId: string) {
  const all = ref<PostCreatedEvent[]>([])
  const seen = new Set<string>()

  let pending: PostCreatedEvent[] = []
  let flushScheduled = false

  /**
   * Hängt eine Charge an all.value an und wendet dabei den Ringpuffer an:
   * überschreitet das Ergebnis MAX_POSTS_PER_FEED, fallen die ältesten
   * Posts heraus — und ihre post_id verlässt auch das seen-Set, sonst
   * würde ein später erneut eintreffender alter Post fälschlich als
   * Duplikat verworfen.
   */
  function appendBatch(batch: PostCreatedEvent[]): void {
    if (batch.length === 0) return
    const next = all.value.concat(batch)
    const overflow = next.length - MAX_POSTS_PER_FEED
    if (overflow > 0) {
      const evicted = next.splice(0, overflow)
      for (const p of evicted) seen.delete(p.post_id)
    }
    all.value = next
  }

  function flushPending(): void {
    flushScheduled = false
    if (pending.length === 0) return
    const batch = pending
    pending = []
    appendBatch(batch)
  }

  function scheduleFlushIfNeeded(): void {
    // Ein Hintergrund-Tab bekommt keine Animation Frames, waehrend SSE
    // weiterhin ingest() aufruft. Ohne diese Schranke waere `pending` (und
    // ueber `seen` auch die Dedup-Menge) die neue unbegrenzt wachsende
    // Struktur — genau der Defekt, den der Ringpuffer beheben soll. Ist der
    // Puffer allein schon so gross wie das Feed-Limit, wird er sofort
    // synchron uebernommen; danach greift die Eviction in appendBatch.
    if (pending.length >= MAX_POSTS_PER_FEED) {
      flushPending()
      return
    }
    if (flushScheduled) return
    flushScheduled = true
    scheduleFrame(flushPending)
  }

  function ingest(post: PostCreatedEvent): void {
    if (post.simulation_id !== simulationId) return
    if (seen.has(post.post_id)) return
    seen.add(post.post_id)
    pending.push(post)
    scheduleFlushIfNeeded()
  }

  /**
   * Nimmt eine Liste in einem Durchgang auf. Laeuft bewusst ueber denselben
   * `pending`-Puffer wie ingest() und flusht danach synchron: schriebe die
   * Funktion direkt in all.value, koennte ein bereits gepufferter, aber noch
   * nicht uebernommener Post nach den hier ergaenzten landen — die Liste
   * waere dann nicht mehr in Eingangsreihenfolge, was Ringpuffer-Eviction
   * und activityRate verfaelscht.
   */
  function ingestMany(posts: PostCreatedEvent[]): void {
    for (const post of posts) {
      if (post.simulation_id !== simulationId) continue
      if (seen.has(post.post_id)) continue
      seen.add(post.post_id)
      pending.push(post)
    }
    flushPending()
  }

  function clear(): void {
    all.value = []
    seen.clear()
    pending = []
    flushScheduled = false
  }

  const redditPosts = computed(() => all.value.filter((p) => p.platform === 'reddit'))

  const twitterPosts = computed(() =>
    [...all.value.filter((p) => p.platform === 'twitter')].sort((a, b) =>
      b.timestamp.localeCompare(a.timestamp),
    ),
  )

  const redditTree = computed<RedditNode[]>(() => {
    const byId = new Map<string, RedditNode>()
    const roots: RedditNode[] = []

    for (const p of redditPosts.value) {
      byId.set(p.post_id, { ...p, children: [] })
    }

    for (const p of redditPosts.value) {
      const node = byId.get(p.post_id)!
      if (p.parent_post_id && byId.has(p.parent_post_id)) {
        byId.get(p.parent_post_id)!.children.push(node)
      } else {
        roots.push(node)
      }
    }

    return roots
  })

  /**
   * Die jüngsten Posts beider Plattformen in Eingangsreihenfolge — Datenquelle
   * der Resonanz-Leiste (#1209 5b). Dasselbe Fenster wie activityRate, damit
   * Leiste und Rate denselben Ausschnitt beschreiben.
   */
  const recentPosts = computed<PostCreatedEvent[]>(() => all.value.slice(-30))

  /**
   * Chronologisch aufsteigende Gesamtliste beider Plattformen — Datenquelle
   * fuer `FeedTimeline` (Slice UI-2b, §2.5). Filter (Plattform/Runde/Persona/
   * Freitext) liegen bei der aufrufenden View, nicht hier.
   */
  const flatTimeline = computed<PostCreatedEvent[]>(() =>
    [...all.value].sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
  )

  const byIdMap = computed<Map<string, PostCreatedEvent>>(() => {
    const map = new Map<string, PostCreatedEvent>()
    for (const p of all.value) map.set(p.post_id, p)
    return map
  })

  /** Loest einen Post ueber seine post_id auf — z.B. fuer Repost-Referenzen. */
  function byId(postId: string): PostCreatedEvent | undefined {
    return byIdMap.value.get(postId)
  }

  const activityRate = computed<number>(() => {
    const recent = all.value.slice(-30)
    if (recent.length < 2) return 0
    const first = Date.parse(recent[0].timestamp)
    const last = Date.parse(recent[recent.length - 1].timestamp)
    const minutes = Math.max((last - first) / 60_000, 1 / 60)
    return recent.length / minutes
  })

  return {
    redditPosts,
    twitterPosts,
    redditTree,
    recentPosts,
    activityRate,
    flatTimeline,
    byId,
    ingest,
    ingestMany,
    clear,
    flushPending,
  }
}

export function useSimFeed(simulationId: string) {
  if (!stores.has(simulationId)) {
    // LRU-Eviction: wenn Limit erreicht, ältesten Eintrag entfernen.
    if (stores.size >= MAX_STORES) {
      const oldestKey = stores.keys().next().value
      if (oldestKey !== undefined) stores.delete(oldestKey)
    }
    stores.set(simulationId, createStore(simulationId))
  }
  return stores.get(simulationId)!
}

/**
 * clearSimFeed — entfernt den Store für eine simulationId.
 * Wird in StepSimulationFeedView.vue onBeforeUnmount aufgerufen.
 */
export function clearSimFeed(simulationId: string): void {
  stores.delete(simulationId)
}

/**
 * resetSimFeedStore — nur für Tests: entfernt gespeicherten Store.
 * @deprecated Verwende clearSimFeed() stattdessen.
 */
export function resetSimFeedStore(simulationId: string): void {
  stores.delete(simulationId)
}
