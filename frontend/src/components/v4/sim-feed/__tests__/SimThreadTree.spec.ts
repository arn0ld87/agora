/**
 * SimThreadTree — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.8.
 * Deckt: Baumaufbau ueber parentIdOf (Reddit-Baum + Twitter-Flachliste),
 * orphan-Chip, loading-Skeleton, maxDepth-Show-more und openThread-Bubbling.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => (params ? `${key}:${params.count}` : key),
    te: () => true,
  }),
}))

import SimThreadTree from '../SimThreadTree.vue'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    persona_name: 'Alice',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'Hallo',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

describe('SimThreadTree', () => {
  it('loading zeigt nur die Wurzel plus Skeleton-Zeilen', () => {
    const root = mkPost({ post_id: 'root-1' })
    const w = mount(SimThreadTree, { props: { root, nodes: [], loading: true } })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.findAll('.fi-root')).toHaveLength(1)
  })

  it('baut einen Reddit-Baum ueber parent_comment_id', () => {
    const root = mkPost({ post_id: 'root-1' })
    const nodes = [
      mkPost({ post_id: 'c-1', parent_post_id: 'root-1' }),
      mkPost({ post_id: 'c-2', parent_comment_id: 'c-1', parent_post_id: 'root-1' }),
    ]
    const w = mount(SimThreadTree, { props: { root, nodes, loading: false } })
    // Wurzel + zwei verschachtelte Antworten
    expect(w.findAll('.fi-root')).toHaveLength(3)
  })

  it('Twitter-Antworten mit nur parent_post_id ergeben eine flache Liste unter der Wurzel', () => {
    const root = mkPost({ post_id: 'root-1', platform: 'twitter' })
    const nodes = [
      mkPost({ post_id: 'reply-1', platform: 'twitter', parent_post_id: 'root-1', kind: 'comment' }),
      mkPost({ post_id: 'reply-2', platform: 'twitter', parent_post_id: 'root-1', kind: 'comment' }),
    ]
    const w = mount(SimThreadTree, { props: { root, nodes, loading: false } })
    expect(w.findAll('.fi-root')).toHaveLength(3)
  })

  it('ein Knoten mit unbekanntem Elternteil landet best-effort direkt unter der Wurzel', () => {
    const root = mkPost({ post_id: 'root-1' })
    const nodes = [mkPost({ post_id: 'stray-1', parent_comment_id: 'unbekannt-im-snapshot' })]
    const w = mount(SimThreadTree, { props: { root, nodes, loading: false } })
    expect(w.findAll('.fi-root')).toHaveLength(2)
  })

  it('orphan-Chip erscheint, wenn die Wurzel selbst noch eine Elternkante hat', () => {
    const root = mkPost({ post_id: 'root-1', parent_post_id: 'unbekannt' })
    const w = mount(SimThreadTree, { props: { root, nodes: [], loading: false } })
    expect(w.get('[role="status"].stt-orphan-chip').text()).toBe('feed.threadTree.orphan')
  })

  it('kein orphan-Chip, wenn die Wurzel keine Elternkante hat', () => {
    const root = mkPost({ post_id: 'root-1', parent_post_id: null })
    const w = mount(SimThreadTree, { props: { root, nodes: [], loading: false } })
    expect(w.find('.stt-orphan-chip').exists()).toBe(false)
  })

  it('maxDepth begrenzt die Rekursion und zeigt "weitere anzeigen" statt der Kinder', () => {
    const root = mkPost({ post_id: 'root-1' })
    const nodes = [
      mkPost({ post_id: 'd1', parent_post_id: 'root-1' }),
      mkPost({ post_id: 'd2', parent_comment_id: 'd1' }),
    ]
    const w = mount(SimThreadTree, { props: { root, nodes, loading: false, maxDepth: 1 } })
    // Wurzel + d1 (Tiefe 1) sichtbar, d2 (Tiefe 2) nicht mehr — statt dessen der Button.
    expect(w.findAll('.fi-root')).toHaveLength(2)
    expect(w.get('.stl-show-more').text()).toBe('feed.showMoreReplies:1')
  })

  it('openThread von einem verschachtelten FeedItem bubbelt bis zur Wurzel-Komponente', async () => {
    // FeedItem.open() adressiert immer die Strang-Wurzel (root_post_id ??
    // parent_post_id ?? post_id) — der Klick auf die Antwort 'c-1' emittiert
    // darum 'root-1', nicht 'c-1' selbst (siehe FeedItem.vue threadPostId).
    const root = mkPost({ post_id: 'root-1' })
    const nodes = [mkPost({ post_id: 'c-1', parent_post_id: 'root-1' })]
    const w = mount(SimThreadTree, { props: { root, nodes, loading: false } })
    const items = w.findAll('.fi-root')
    await items[1].trigger('click')
    expect(w.emitted('openThread')?.[0]).toEqual(['root-1'])
  })
})
