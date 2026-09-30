/**
 * SimRoundsList — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.9.
 * Deckt loading/empty/error-Zustaende, die Gruppierung von Plattform-
 * Eintraegen pro Runde, die kanonische Aktionsart-Reihenfolge und das
 * select-Event ab.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import type { RoundSummary } from '@/contracts/simActionContract'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimRoundsList from '../SimRoundsList.vue'

function mkRound(overrides: Partial<RoundSummary> = {}): RoundSummary {
  return {
    round_num: 0,
    platform: 'reddit',
    action_counts: {},
    ...overrides,
  }
}

describe('SimRoundsList', () => {
  it('loading zeigt 5 Skeleton-Zeilen mit aria-busy', () => {
    const w = mount(SimRoundsList, {
      props: { rounds: [], activeRound: null, streamState: 'open', loading: true },
    })
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.findAll('.srl-skeleton-row')).toHaveLength(5)
  })

  it('error zeigt ein Banner mit Retry-Button, der retry emittiert', async () => {
    const w = mount(SimRoundsList, {
      props: {
        rounds: [],
        activeRound: null,
        streamState: 'open',
        loading: false,
        error: { code: 'x', message: 'kaputt' },
      },
    })
    expect(w.get('[role="alert"]').text()).toContain('feed.rounds.error')
    await w.get('.srl-retry').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })

  it('leere Rundenliste zeigt den Empty-State', () => {
    const w = mount(SimRoundsList, {
      props: { rounds: [], activeRound: null, streamState: 'open', loading: false },
    })
    expect(w.get('[role="status"]').text()).toBe('feed.rounds.empty')
  })

  it('gruppiert reddit- und twitter-Eintraege derselben Runde zu einer Zeile', () => {
    const rounds = [
      mkRound({ round_num: 0, platform: 'reddit', action_counts: { CREATE_POST: 2 } }),
      mkRound({ round_num: 0, platform: 'twitter', action_counts: { CREATE_POST: 1 } }),
      mkRound({ round_num: 1, platform: 'reddit', action_counts: {} }),
    ]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: null, streamState: 'open', loading: false },
    })
    expect(w.findAll('.srl-item')).toHaveLength(2)
    // Runde 0 hat zwei Plattform-Bloecke (reddit + twitter)
    const firstRow = w.findAll('.srl-item')[0]
    expect(firstRow.findAll('.srl-platform-block')).toHaveLength(2)
  })

  it('zeigt Aktionsarten in kanonischer Reihenfolge mit Zaehlern', () => {
    const rounds = [
      mkRound({
        round_num: 0,
        platform: 'reddit',
        action_counts: { LIKE_POST: 5, CREATE_POST: 3, CREATE_COMMENT: 2 },
      }),
    ]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: null, streamState: 'open', loading: false },
    })
    const counts = w.findAll('.srl-count').map((c) => c.text())
    // CREATE_POST vor CREATE_COMMENT vor LIKE_POST (kanonische Reihenfolge,
    // nicht Einfuegereihenfolge).
    expect(counts).toEqual([
      'feed.actionType.CREATE_POST: 3',
      'feed.actionType.CREATE_COMMENT: 2',
      'feed.actionType.LIKE_POST: 5',
    ])
  })

  it('ein unbekannter Aktionsart-Schluessel (Datendrift) zeigt den Rohwert statt einer unaufgeloesten i18n-Kette', () => {
    const rounds = [mkRound({ round_num: 0, platform: 'reddit', action_counts: { CUSTOM_TYPE: 1 } })]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: null, streamState: 'open', loading: false },
    })
    expect(w.get('.srl-count').text()).toBe('CUSTOM_TYPE: 1')
  })

  it('Runde ohne Aktionen zeigt den "keine Aktionen"-Hinweis', () => {
    const rounds = [mkRound({ round_num: 0, platform: 'reddit', action_counts: {} })]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: null, streamState: 'open', loading: false },
    })
    expect(w.find('.srl-no-actions').exists()).toBe(true)
  })

  it('aria-current markiert die aktive Runde', () => {
    const rounds = [mkRound({ round_num: 0 }), mkRound({ round_num: 1, action_counts: {} })]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: 1, streamState: 'open', loading: false },
    })
    const rows = w.findAll('.srl-row')
    expect(rows[0].attributes('aria-current')).toBeUndefined()
    expect(rows[1].attributes('aria-current')).toBe('true')
  })

  it('Klick auf eine Zeile emittiert select mit round_num', async () => {
    const rounds = [mkRound({ round_num: 3 })]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: null, streamState: 'open', loading: false },
    })
    await w.get('.srl-row').trigger('click')
    expect(w.emitted('select')?.[0]).toEqual([3])
  })

  it('Enter auf einer Zeile emittiert select (Tastatur)', async () => {
    const rounds = [mkRound({ round_num: 5 })]
    const w = mount(SimRoundsList, {
      props: { rounds, activeRound: null, streamState: 'open', loading: false },
    })
    await w.get('.srl-row').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('select')?.[0]).toEqual([5])
  })
})
