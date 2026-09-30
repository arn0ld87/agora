/**
 * SimThreadList — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.7.
 * Deckt loading/empty(no_data|filter)/data-Zustaende, Runden-Chip-Format und
 * das open-Event per Klick/Tastatur ab.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import type { SimThreadListEntry } from '../SimThreadList.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => (params ? `${key}:${JSON.stringify(params)}` : key) }),
}))

import SimThreadList from '../SimThreadList.vue'

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
    body: 'Hallo Welt',
    timestamp: '2026-05-15T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

function mkEntry(overrides: Partial<SimThreadListEntry> = {}): SimThreadListEntry {
  return {
    root: mkPost(),
    replyCount: 0,
    repostCount: 0,
    quoteCount: 0,
    lastActivityAt: '2026-05-15T12:00:00Z',
    activeRounds: [],
    ...overrides,
  }
}

describe('SimThreadList', () => {
  it('loading zeigt 5 Skeleton-Zeilen mit aria-busy', () => {
    const w = mount(SimThreadList, { props: { threads: [], loading: true, emptyReason: null } })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.findAll('.stl2-skeleton-row')).toHaveLength(5)
  })

  it('emptyReason=no_data zeigt den generischen Empty-Text', () => {
    const w = mount(SimThreadList, { props: { threads: [], loading: false, emptyReason: 'no_data' } })
    expect(w.get('[role="status"]').text()).toBe('feed.threadList.empty')
  })

  it('emptyReason=filter zeigt den Filter-spezifischen Empty-Text', () => {
    const w = mount(SimThreadList, { props: { threads: [], loading: false, emptyReason: 'filter' } })
    expect(w.get('[role="status"]').text()).toBe('feed.threadList.emptyFiltered')
  })

  it('rendert Wurzel-Persona, Kurztext, Plattform-Marker und Counts', () => {
    const entry = mkEntry({
      root: mkPost({ persona_name: 'Bob', body: 'Kurztext', platform: 'twitter' }),
      replyCount: 2,
      repostCount: 1,
      quoteCount: 3,
    })
    const w = mount(SimThreadList, { props: { threads: [entry], loading: false, emptyReason: null } })
    expect(w.text()).toContain('Bob')
    expect(w.text()).toContain('Kurztext')
    expect(w.get('.stl2-platform').text()).toBe('T')
  })

  it('zeigt den Runden-Chip als Einzelwert oder Bereich', () => {
    const single = mkEntry({ activeRounds: [2] })
    const range = mkEntry({ root: mkPost({ post_id: 'p-2' }), activeRounds: [1, 2, 3] })
    const w = mount(SimThreadList, { props: { threads: [single, range], loading: false, emptyReason: null } })
    const chips = w.findAll('.stl2-round-chip')
    expect(chips[0].text()).toBe('R2')
    expect(chips[1].text()).toBe('R1–3')
  })

  it('kein Runden-Chip, wenn activeRounds leer ist', () => {
    const entry = mkEntry({ activeRounds: [] })
    const w = mount(SimThreadList, { props: { threads: [entry], loading: false, emptyReason: null } })
    expect(w.find('.stl2-round-chip').exists()).toBe(false)
  })

  it('Klick auf eine Zeile emittiert open mit der post_id der Wurzel', async () => {
    const entry = mkEntry({ root: mkPost({ post_id: 'root-click' }) })
    const w = mount(SimThreadList, { props: { threads: [entry], loading: false, emptyReason: null } })
    await w.get('[role="button"]').trigger('click')
    expect(w.emitted('open')?.[0]).toEqual(['root-click'])
  })

  it('Enter/Space auf einer Zeile emittiert open (Tastatur)', async () => {
    const entry = mkEntry({ root: mkPost({ post_id: 'root-key' }) })
    const w = mount(SimThreadList, { props: { threads: [entry], loading: false, emptyReason: null } })
    await w.get('[role="button"]').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('open')?.[0]).toEqual(['root-key'])
  })
})
