import { describe, it, expect } from 'vitest'
import {
  buildRoundTicks,
  secondsPerRound,
  buildActorStats,
  formatElapsed,
  formatSecondsPerRound,
} from '../useSimulationLiveMetrics'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-1',
    post_id: `p-${Math.random().toString(36).slice(2)}`,
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    persona_name: 'Alice',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'Test',
    timestamp: '2026-09-06T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

describe('buildRoundTicks', () => {
  it('markiert Runden vor der aktuellen als done, die aktuelle als now, den Rest als todo', () => {
    const ticks = buildRoundTicks(3, 5)
    expect(ticks).toEqual([
      { round: 1, state: 'done' },
      { round: 2, state: 'done' },
      { round: 3, state: 'now' },
      { round: 4, state: 'todo' },
      { round: 5, state: 'todo' },
    ])
  })

  it('liefert eine leere Achse ohne Rundenzahl', () => {
    expect(buildRoundTicks(0, 0)).toEqual([])
  })
})

describe('secondsPerRound', () => {
  it('teilt vergangene Sekunden durch die aktuelle Runde', () => {
    expect(secondsPerRound(63, 3)).toBe(21)
  })

  it('liefert null ohne gelaufene Runde', () => {
    expect(secondsPerRound(10, 0)).toBeNull()
  })

  it('liefert null ohne vergangene Zeit', () => {
    expect(secondsPerRound(0, 3)).toBeNull()
  })
})

describe('buildActorStats', () => {
  it('gruppiert Posts nach persona_id und zaehlt Beitraege', () => {
    const posts = [
      mkPost({ persona_id: 'alice', persona_name: 'Alice' }),
      mkPost({ persona_id: 'alice', persona_name: 'Alice' }),
      mkPost({ persona_id: 'bob', persona_name: 'Bob' }),
    ]
    const stats = buildActorStats(posts)
    expect(stats).toEqual([
      { personaId: 'alice', personaName: 'Alice', count: 2, isActive: true },
      { personaId: 'bob', personaName: 'Bob', count: 1, isActive: true },
    ])
  })

  it('markiert nur Akteure aus dem juengsten Fenster als aktiv', () => {
    const posts = [
      mkPost({ persona_id: 'alice', persona_name: 'Alice' }),
      ...Array.from({ length: 5 }, () => mkPost({ persona_id: 'bob', persona_name: 'Bob' })),
    ]
    const stats = buildActorStats(posts, 2)
    const alice = stats.find((s) => s.personaId === 'alice')
    expect(alice?.isActive).toBe(false)
    const bob = stats.find((s) => s.personaId === 'bob')
    expect(bob?.isActive).toBe(true)
  })
})

describe('formatElapsed', () => {
  it('formatiert unter einer Stunde als mm:ss', () => {
    expect(formatElapsed(125)).toBe('02:05')
  })

  it('formatiert ab einer Stunde als hh:mm:ss', () => {
    expect(formatElapsed(3725)).toBe('01:02:05')
  })
})

describe('formatSecondsPerRound', () => {
  it('formatiert mit einer Nachkommastelle', () => {
    expect(formatSecondsPerRound(21.456)).toBe('21.5 s')
  })

  it('zeigt einen Platzhalter wenn nicht ableitbar', () => {
    expect(formatSecondsPerRound(null)).toBe('—')
  })
})
