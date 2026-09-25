/**
 * Listen-Invalidierung über Supabase Realtime (#1618).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick, reactive } from 'vue'

const WS_A = 'aaaaaaaa-0000-4000-8000-00000000000a'
const WS_B = 'bbbbbbbb-0000-4000-8000-00000000000b'

type Handler = (payload: unknown) => void
interface FakeChannel {
  name: string
  bindings: { filter: Record<string, string>; handler: Handler }[]
  on: (type: string, filter: Record<string, string>, handler: Handler) => FakeChannel
  subscribe: ReturnType<typeof vi.fn>
}

const fake = vi.hoisted(() => ({
  channels: [] as unknown[],
  removeChannel: null as unknown as ReturnType<typeof import('vitest').vi.fn>,
  client: null as unknown,
}))

vi.mock('../../auth/supabaseClient', () => ({ getSupabaseClient: () => fake.client }))

const auth = reactive({
  jwtEnabled: true,
  config: { realtime_enabled: true } as { realtime_enabled: boolean } | null,
  session: { access_token: 'tok' } as object | null,
  activeWorkspaceId: WS_A as string | null,
})
const storeMode = { throws: false }
vi.mock('../../store/auth', () => ({
  useAuthStore: () => {
    if (storeMode.throws) throw new Error('getActivePinia was called with no active Pinia')
    return auth
  },
}))

import {
  INVALIDATION_INTERVAL_MS,
  _resetListInvalidation,
  onListInvalidated,
} from '../listInvalidation'

function makeClient() {
  fake.channels = []
  fake.removeChannel = vi.fn(async () => 'ok')
  fake.client = {
    channel: (name: string) => {
      const ch: FakeChannel = {
        name,
        bindings: [],
        on(_type, filter, handler) {
          ch.bindings.push({ filter, handler })
          return ch
        },
        subscribe: vi.fn(),
      }
      fake.channels.push(ch)
      return ch
    },
    removeChannel: fake.removeChannel,
  }
}

function channels(): FakeChannel[] {
  return fake.channels as FakeChannel[]
}

function emit(ch: FakeChannel, payload: Record<string, unknown>): void {
  // Alle Bindungen teilen denselben Handler; der Server wählt nach Filter.
  ch.bindings[0].handler(payload)
}

function change(table: string, workspaceId: string, eventType = 'UPDATE') {
  return { schema: 'agora', table, eventType, new: { id: 'x', workspace_id: workspaceId }, old: {} }
}

beforeEach(() => {
  vi.useFakeTimers()
  makeClient()
  auth.jwtEnabled = true
  auth.config = { realtime_enabled: true }
  auth.session = { access_token: 'tok' }
  auth.activeWorkspaceId = WS_A
  storeMode.throws = false
})

afterEach(() => {
  _resetListInvalidation()
  vi.useRealTimers()
})

describe('Kanal', () => {
  it('abonniert INSERT und UPDATE der vier Tabellen, gefiltert auf den Workspace', () => {
    onListInvalidated(['runs'], vi.fn())

    expect(channels()).toHaveLength(1)
    const [ch] = channels()
    expect(ch.name).toBe(`agora-lists:${WS_A}`)
    expect(ch.subscribe).toHaveBeenCalledTimes(1)
    const seen = ch.bindings.map((b) => `${b.filter.table}:${b.filter.event}`).sort()
    expect(seen).toEqual(
      ['projects', 'reports', 'runs', 'simulations'].flatMap((t) => [`${t}:INSERT`, `${t}:UPDATE`]).sort(),
    )
    for (const b of ch.bindings) {
      expect(b.filter.schema).toBe('agora')
      expect(b.filter.filter).toBe(`workspace_id=eq.${WS_A}`)
    }
  })

  it.each([
    ['ohne realtime_enabled', () => { auth.config = { realtime_enabled: false } }],
    ['ohne Session', () => { auth.session = null }],
    ['ohne aktiven Workspace', () => { auth.activeWorkspaceId = null }],
    ['ohne JWT', () => { auth.jwtEnabled = false }],
  ])('öffnet keinen Kanal %s', (_label, arrange) => {
    arrange()
    onListInvalidated(['runs'], vi.fn())
    expect(channels()).toHaveLength(0)
  })

  it('bleibt ohne aktive Pinia still', () => {
    storeMode.throws = true
    const off = onListInvalidated(['runs'], vi.fn())
    expect(channels()).toHaveLength(0)
    off()
  })

  it('wechselt den Kanal mit dem Workspace', async () => {
    onListInvalidated(['runs'], vi.fn())
    auth.activeWorkspaceId = WS_B
    await nextTick()

    expect(fake.removeChannel).toHaveBeenCalledWith(channels()[0])
    expect(channels()[1].name).toBe(`agora-lists:${WS_B}`)
  })

  it('schließt den Kanal nach dem letzten Abmelden', () => {
    const offA = onListInvalidated(['runs'], vi.fn())
    const offB = onListInvalidated(['projects'], vi.fn())
    offA()
    expect(fake.removeChannel).not.toHaveBeenCalled()
    offB()
    expect(fake.removeChannel).toHaveBeenCalledWith(channels()[0])
  })
})

describe('Ereignisse', () => {
  it('invalidiert nur die passende Liste', () => {
    const runs = vi.fn()
    const projects = vi.fn()
    onListInvalidated(['runs'], runs)
    onListInvalidated(['projects'], projects)

    emit(channels()[0], change('runs', WS_A))
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS)

    expect(runs).toHaveBeenCalledWith('runs')
    expect(projects).not.toHaveBeenCalled()
  })

  it('ignoriert ein Ereignis aus einem fremden Workspace', () => {
    const runs = vi.fn()
    onListInvalidated(['runs'], runs)

    emit(channels()[0], change('runs', WS_B))
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS * 2)

    expect(runs).not.toHaveBeenCalled()
  })

  it.each([
    ['DELETE', change('runs', WS_A, 'DELETE')],
    ['fremdes Schema', { ...change('runs', WS_A), schema: 'public' }],
    ['unbekannte Tabelle', change('llm_profiles', WS_A)],
    ['ohne workspace_id', { schema: 'agora', table: 'runs', eventType: 'UPDATE', new: { id: 'x' } }],
  ])('ignoriert %s', (_label, payload) => {
    const runs = vi.fn()
    onListInvalidated(['runs'], runs)

    emit(channels()[0], payload)
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS * 2)

    expect(runs).not.toHaveBeenCalled()
  })

  it('bündelt eine Folge von Ereignissen zu einem Nachladen', () => {
    const runs = vi.fn()
    onListInvalidated(['runs'], runs)

    for (let i = 0; i < 5; i++) emit(channels()[0], change('runs', WS_A))
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS)
    expect(runs).toHaveBeenCalledTimes(1)

    emit(channels()[0], change('runs', WS_A))
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS)
    expect(runs).toHaveBeenCalledTimes(2)
  })

  it('ruft nach dem Abmelden nicht mehr nach', () => {
    const runs = vi.fn()
    const keep = vi.fn()
    const off = onListInvalidated(['runs'], runs)
    onListInvalidated(['projects'], keep)

    emit(channels()[0], change('runs', WS_A))
    off()
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS)

    expect(runs).not.toHaveBeenCalled()
  })

  it('verwirft ein ausstehendes Nachladen beim Workspace-Wechsel', async () => {
    const runs = vi.fn()
    onListInvalidated(['runs'], runs)

    emit(channels()[0], change('runs', WS_A))
    auth.activeWorkspaceId = WS_B
    await nextTick()
    vi.advanceTimersByTime(INVALIDATION_INTERVAL_MS)

    expect(runs).not.toHaveBeenCalled()
  })
})
