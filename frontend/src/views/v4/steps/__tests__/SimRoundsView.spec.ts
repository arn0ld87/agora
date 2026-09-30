/**
 * SimRoundsView — Slice UI-2b (#1713), Commit 4
 * (docs/design/simulation-feed.md §2.9).
 *
 * Prueft: Runden werden ueber getSimulationRounds geladen, Fehler zeigen
 * den Retry-Banner, ein select-Event schreibt ?round= in die Query
 * (router.replace), bestehende Query-Parameter bleiben erhalten.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { resetSimFeedStore } from '@/composables/useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import type { RoundSummary } from '@/contracts/simActionContract'

let roundsResult: { success: boolean; data: { rounds: RoundSummary[] } } | null = null
let roundsShouldFail = false

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshot: () => Promise.resolve([]),
  getSimulationRounds: () => {
    if (roundsShouldFail) return Promise.reject(new Error('network'))
    return Promise.resolve(roundsResult)
  },
}))

vi.mock('@/api/envelope', () => ({
  unwrap: (envelope: { data: unknown }) => envelope.data,
}))

vi.mock('@/composables/useEventStream', () => ({
  useEventStream: (_id: string, _handlers: { post_created?: (data: PostCreatedEvent) => void }) => ({
    isStreaming: { value: true },
    error: { value: null },
    lastEventAt: { value: null },
    lastTraceId: { value: null },
    start: vi.fn(() => Promise.resolve()),
    stop: vi.fn(),
  }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

const routerReplaceMock = vi.fn()
let currentQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { simulationId: 'test-sim-rounds' }, query: currentQuery }),
  useRouter: () => ({ push: vi.fn(), replace: routerReplaceMock }),
}))

import SimRoundsView from '../SimRoundsView.vue'

describe('SimRoundsView', () => {
  beforeEach(() => {
    resetSimFeedStore('test-sim-rounds')
    roundsResult = { success: true, data: { rounds: [] } }
    roundsShouldFail = false
    currentQuery = {}
    routerReplaceMock.mockClear()
  })

  it('laedt die Rundenliste beim Mount und zeigt sie in SimRoundsList', async () => {
    roundsResult = {
      success: true,
      data: {
        rounds: [
          { round_num: 0, platform: 'reddit', action_counts: { CREATE_POST: 2 } },
          { round_num: 1, platform: 'reddit', action_counts: {} },
        ],
      },
    }
    const w = mount(SimRoundsView)
    await flushPromises()
    expect(w.findAll('.srl-item')).toHaveLength(2)
  })

  it('ein Ladefehler zeigt den Retry-Banner statt einer leeren Liste', async () => {
    roundsShouldFail = true
    const w = mount(SimRoundsView)
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
  })

  it('Klick auf eine Runde schreibt ?round= per router.replace, bestehende Query bleibt erhalten', async () => {
    currentQuery = { platform: 'reddit' }
    roundsResult = { success: true, data: { rounds: [{ round_num: 2, platform: 'reddit', action_counts: {} }] } }
    const w = mount(SimRoundsView)
    await flushPromises()

    await w.get('.srl-row').trigger('click')

    expect(routerReplaceMock).toHaveBeenCalledWith({ query: { platform: 'reddit', round: '2' } })
  })

  it('leere Rundenliste zeigt den Empty-State', async () => {
    const w = mount(SimRoundsView)
    await flushPromises()
    expect(w.text()).toContain('feed.rounds.empty')
  })
})
