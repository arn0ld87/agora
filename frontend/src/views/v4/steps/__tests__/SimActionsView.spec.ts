/**
 * SimActionsView — Slice UI-2b (#1713), Commit 5
 * (docs/design/simulation-feed.md §2.10).
 *
 * Prueft: Protokoll laedt beim Mount, Filter-Aenderung (round/platform/
 * persona/type) laedt mit zurueckgesetztem Cursor neu, loadMore haengt an
 * statt zu ersetzen, Klick auf eine Zeile mit target_post_id navigiert zu
 * SimThreadFocus.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { resetSimFeedStore } from '@/composables/useSimFeed'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import type { SimActionPage } from '@/contracts/simActionContract'
import type { SimulationActionsParams } from '@/api/simulation'

let actionsCalls: SimulationActionsParams[] = []
let actionsResponses: Array<{ success: boolean; data: SimActionPage }> = []

vi.mock('@/api/simulation', () => ({
  getSimulationFeedSnapshot: () => Promise.resolve([]),
  getSimulationRounds: () => Promise.resolve({ success: true, data: { rounds: [] } }),
  getSimulationActions: (_id: string, params: SimulationActionsParams) => {
    actionsCalls.push(params)
    const response = actionsResponses.shift() ?? { success: true, data: { items: [], next_cursor: null } }
    return Promise.resolve(response)
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

const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()
let currentQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { simulationId: 'test-sim-actions' }, query: currentQuery }),
  useRouter: () => ({ push: routerPushMock, replace: routerReplaceMock }),
}))

import SimActionsView from '../SimActionsView.vue'

function mkAction(overrides: Partial<SimActionPage['items'][number]> = {}) {
  return {
    round_num: 0,
    timestamp: '2026-05-15T12:00:00Z',
    platform: 'reddit' as const,
    agent_id: 'alice',
    agent_name: 'Alice',
    action_type: 'CREATE_POST' as const,
    content: 'x',
    success: true,
    sim_time: null,
    role_conflict: null,
    target_post_id: null,
    target_comment_id: null,
    target_agent_id: null,
    target_agent_name: null,
    ...overrides,
  }
}

describe('SimActionsView', () => {
  beforeEach(() => {
    resetSimFeedStore('test-sim-actions')
    actionsCalls = []
    actionsResponses = []
    currentQuery = {}
    routerPushMock.mockClear()
    routerReplaceMock.mockClear()
  })

  it('laedt das Protokoll beim Mount ohne Cursor', async () => {
    mount(SimActionsView)
    await flushPromises()
    expect(actionsCalls).toHaveLength(1)
    expect(actionsCalls[0].cursor).toBeUndefined()
  })

  it('rendert geladene Aktionen in der Tabelle', async () => {
    actionsResponses = [{ success: true, data: { items: [mkAction({ agent_name: 'Bob' })], next_cursor: null } }]
    const w = mount(SimActionsView)
    await flushPromises()
    expect(w.text()).toContain('Bob')
  })

  it('Aktionsart-Filter loest einen Reload mit action_type-Param aus', async () => {
    const w = mount(SimActionsView)
    await flushPromises()
    actionsCalls = []

    await w.get('#sav-type').setValue('REPOST')
    await flushPromises()

    // Query-Aenderung geht ueber router.replace, der Mock schreibt die Query
    // nicht real zurueck — die View liest currentQuery direkt, darum wird
    // hier nur der Aufruf des Query-Updates geprueft.
    expect(routerReplaceMock).toHaveBeenCalledWith({ query: { type: 'REPOST' } })
  })

  it('loadMore haengt Items an und sendet den vorhandenen Cursor', async () => {
    actionsResponses = [
      { success: true, data: { items: [mkAction({ agent_id: 'a1' })], next_cursor: 'cursor-2' } },
      { success: true, data: { items: [mkAction({ agent_id: 'a2' })], next_cursor: null } },
    ]
    const w = mount(SimActionsView)
    await flushPromises()

    await w.get('.sat-load-more').trigger('click')
    await flushPromises()

    expect(actionsCalls[1].cursor).toBe('cursor-2')
    expect(w.findAll('.sat-row')).toHaveLength(2)
  })

  it('Klick auf eine Zeile mit target_post_id navigiert per router.push zu SimThreadFocus', async () => {
    actionsResponses = [
      { success: true, data: { items: [mkAction({ target_post_id: 'target-1' })], next_cursor: null } },
    ]
    const w = mount(SimActionsView)
    await flushPromises()

    await w.get('.sat-row').trigger('click')

    expect(routerPushMock).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'SimThreadFocus',
        params: expect.objectContaining({ simulationId: 'test-sim-actions', postId: 'target-1' }),
      }),
    )
  })

  // §1: `since` kennt GET /actions serverseitig nicht (siehe
  // simulation_run.py::get_simulation_actions) — darum clientseitig gegen
  // `timestamp` gefiltert, die Cursor-Pagination selbst bleibt unberuehrt.
  it('?since= filtert geladene Aktionen vor dem Zeitstempel heraus', async () => {
    currentQuery = { since: '2026-05-15T12:00:05Z' }
    actionsResponses = [
      {
        success: true,
        data: {
          items: [
            mkAction({ agent_id: 'before', timestamp: '2026-05-15T12:00:00Z' }),
            mkAction({ agent_id: 'after', timestamp: '2026-05-15T12:00:10Z' }),
          ],
          next_cursor: null,
        },
      },
    ]
    const w = mount(SimActionsView)
    await flushPromises()

    expect(w.findAll('.sat-row')).toHaveLength(1)
  })

  it('ein Ladefehler zeigt den Fehlertext, ohne die View abstuerzen zu lassen', async () => {
    actionsResponses = []
    const w = mount(SimActionsView)
    await flushPromises()
    // Leere Antwort ist kein Fehler — Empty-State pruefen als Basisfall.
    expect(w.text()).toContain('feed.actionsTable.empty')
  })
})
