/**
 * FeedTimeline — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.5, §4.
 * Deckt loading/empty/error/data-Zustaende und die openThread/retry-Events ab.
 * Virtualisierung selbst (DOM-Knoten-Obergrenze bei 500 Items) ist Gegenstand
 * der Design-Lead-Abnahme (§6.6), nicht dieses Unit-Tests — jsdom liefert
 * keine echten Layout-Maße fuer @tanstack/vue-virtual.
 */
import { describe, it, expect, vi } from 'vitest'
import { computed, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import { resetSimFeedStore } from '@/composables/useSimFeed'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

// @tanstack/vue-virtual misst reale Layout-Groessen (ResizeObserver,
// clientHeight) — jsdom liefert dafuer keine sinnvollen Werte. Der Unit-Test
// deckt FeedTimelines eigene Logik ab (welche Items/Events entstehen), nicht
// die Geometrie der Bibliothek; die Virtualisierungs-Obergrenze bei 500
// Items ist Gegenstand der Design-Lead-Abnahme (§6.6).
vi.mock('@tanstack/vue-virtual', () => ({
  useVirtualizer: (optionsRef: { value: { count: number } }) =>
    computed(() => {
      const count = optionsRef.value.count
      const rows = Array.from({ length: count }, (_, index) => ({ index, start: index * 120 }))
      return {
        getVirtualItems: () => rows,
        getTotalSize: () => count * 120,
        scrollToIndex: () => {},
      }
    }),
}))

import FeedTimeline from '../FeedTimeline.vue'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-ft',
    post_id: 'p-1',
    parent_post_id: null,
    platform: 'twitter',
    persona_id: 'alice',
    persona_name: 'Alice',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'hallo',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

function baseProps(items: PostCreatedEvent[] = []) {
  return {
    items,
    streamState: 'open' as const,
    isSnapshotLoading: false,
    error: null,
  }
}

describe('FeedTimeline', () => {
  it('isSnapshotLoading zeigt drei Skeleton-Zeilen mit aria-busy', () => {
    const w = mount(FeedTimeline, { props: { ...baseProps(), isSnapshotLoading: true } })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.findAll('.ft-skeleton-row')).toHaveLength(3)
  })

  it('leere Liste zeigt den deutschen Empty-State mit Kurzhinweis', () => {
    const w = mount(FeedTimeline, { props: baseProps([]) })
    const empty = w.get('[role="status"].ft-empty')
    expect(empty.text()).toContain('feed.noPosts')
    expect(empty.text()).toContain('feed.noPostsHint')
  })

  it('error zeigt ein Banner mit Retry-Button, der retry emittiert', async () => {
    const w = mount(FeedTimeline, {
      props: { ...baseProps(), error: { code: 'x', message: 'Fehler beim Laden' } },
    })
    const banner = w.get('[role="alert"]')
    expect(banner.text()).toContain('Fehler beim Laden')
    await w.get('.ft-retry').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })

  it('streamState=reconnecting zeigt den Reconnect-Banner', () => {
    const w = mount(FeedTimeline, {
      props: { ...baseProps(), streamState: 'reconnecting' },
    })
    expect(w.text()).toContain('feed.streamLost')
  })

  it('NewItemsPill steht im DOM nach der Timeline (Tab-Reihenfolge Filter -> Timeline -> Pill, §6.9)', async () => {
    resetSimFeedStore('sim-ft')
    const items = [mkPost({ post_id: 'p-1' })]
    const w = mount(FeedTimeline, { props: baseProps(items) })
    await nextTick()

    // Nutzer scrollt vom unteren Rand weg, damit neue Items den Pill statt
    // eines stillen Anhaengens ausloesen (siehe onScroll/isAtBottom).
    const scrollEl = w.get('.ft-scroll').element as HTMLElement
    Object.defineProperty(scrollEl, 'scrollHeight', { value: 2000, configurable: true })
    Object.defineProperty(scrollEl, 'clientHeight', { value: 200, configurable: true })
    Object.defineProperty(scrollEl, 'scrollTop', { value: 0, configurable: true, writable: true })
    await w.get('.ft-scroll').trigger('scroll')

    // Der watch()-Callback auf `items` laeuft nicht bei `immediate: true` —
    // der erste Trigger nach dem Mount erfasst nur die Baseline (siehe
    // FeedTimeline.vue). Erst der zweite setProps-Aufruf zaehlt als
    // "neu angekommen" und erhoeht pillCount.
    await w.setProps({ items: [...items] })
    await w.setProps({ items: [...items, mkPost({ post_id: 'p-2' })] })
    await nextTick()

    expect(w.find('.nip-root').exists()).toBe(true)
    // DOM-Reihenfolge (nicht die visuelle Position): .ft-scroll steht vor
    // dem Pill-Markup, obwohl der Pill visuell darueber liegt
    // (order: -1 in NewItemsPill.vue haelt die Optik).
    const html = w.html()
    expect(html.indexOf('ft-scroll')).toBeLessThan(html.indexOf('nip-root'))
  })

  it('rendert Posts und leitet openThread von FeedItem weiter', async () => {
    resetSimFeedStore('sim-ft')
    const items = [mkPost({ post_id: 'p-1' }), mkPost({ post_id: 'p-2' })]
    const w = mount(FeedTimeline, { props: baseProps(items) })
    expect(w.find('[role="feed"]').exists()).toBe(true)
    const article = w.find('.fi-root')
    expect(article.exists()).toBe(true)
    await article.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('openThread')).toBeTruthy()
  })
})
