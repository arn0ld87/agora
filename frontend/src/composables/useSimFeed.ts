/**
 * useSimFeed — State pro Simulation: Reddit-Thread + Twitter-Flow.
 *
 * Slice FE-Redesign-5 · 2026-05-15
 *
 * Konsumiert PostCreatedEvent (Slice 5-pre), routet nach platform,
 * dedupliziert per post_id, baut Reddit-Reply-Tree, sortiert Twitter
 * nach timestamp DESC.
 *
 * Singleton-Map pro simulationId — reset via clear().
 */

import { computed, ref } from 'vue'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

export interface RedditNode extends PostCreatedEvent {
  children: RedditNode[]
}

const stores = new Map<string, ReturnType<typeof createStore>>()

function createStore(simulationId: string) {
  const all = ref<PostCreatedEvent[]>([])
  const seen = new Set<string>()

  function ingest(post: PostCreatedEvent): void {
    if (post.simulation_id !== simulationId) return
    if (seen.has(post.post_id)) return
    seen.add(post.post_id)
    all.value.push(post)
  }

  function clear(): void {
    all.value = []
    seen.clear()
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

  const activityRate = computed<number>(() => {
    const recent = all.value.slice(-30)
    if (recent.length < 2) return 0
    const first = Date.parse(recent[0].timestamp)
    const last = Date.parse(recent[recent.length - 1].timestamp)
    const minutes = Math.max((last - first) / 60_000, 1 / 60)
    return recent.length / minutes
  })

  return { redditPosts, twitterPosts, redditTree, activityRate, ingest, clear }
}

export function useSimFeed(simulationId: string) {
  if (!stores.has(simulationId)) {
    stores.set(simulationId, createStore(simulationId))
  }
  return stores.get(simulationId)!
}

/**
 * resetSimFeedStore — nur für Tests: entfernt gespeicherten Store.
 */
export function resetSimFeedStore(simulationId: string): void {
  stores.delete(simulationId)
}
