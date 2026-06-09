// Task 1 — useSimClock Composable-Tests.
//
// Sichert ab:
// - ingest() setzt start beim ersten sim_time != null
// - currentSimTime ist monoton (kleinere Werte werden ignoriert)
// - elapsed extrapoliert via 1-Hz-Forecast
// - stop() gibt Interval frei und reset-et State

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { useSimClock, clearSimClock } from '../useSimClock'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

function makeEvent(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim-clock',
    post_id: 'p-' + Math.random().toString(36).slice(2),
    parent_post_id: null,
    platform: 'twitter',
    persona_id: 'persona-1',
    voice_register: 'casual',
    is_simulated: true,
    body: 'tick',
    timestamp: '2026-05-16T10:00:00.000Z',
    sentiment: null,
    score: 0,
    ...overrides,
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-05-16T08:00:00Z'))
  clearSimClock('sim-clock')
})

afterEach(() => {
  vi.useRealTimers()
  clearSimClock('sim-clock')
})

describe('useSimClock', () => {
  it('setzt start auf den ersten gesehenen sim_time', () => {
    const clock = useSimClock('sim-clock')
    expect(clock.start.value).toBeNull()
    expect(clock.currentSimTime.value).toBeNull()

    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:00:00.000Z' }))

    expect(clock.start.value).toEqual(new Date('2026-05-16T10:00:00.000Z'))
    expect(clock.currentSimTime.value).toEqual(new Date('2026-05-16T10:00:00.000Z'))
  })

  it('ignoriert sim_time === null oder fehlend', () => {
    const clock = useSimClock('sim-clock')
    clock.ingest(makeEvent({ sim_time: null }))
    clock.ingest(makeEvent({}))
    expect(clock.start.value).toBeNull()
    expect(clock.currentSimTime.value).toBeNull()
  })

  it('ist monoton — out-of-order kleinere Werte werden ignoriert', () => {
    const clock = useSimClock('sim-clock')
    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:00:00.000Z' }))
    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:30:00.000Z' }))
    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:15:00.000Z' })) // < latest

    expect(clock.currentSimTime.value).toEqual(new Date('2026-05-16T10:30:00.000Z'))
  })

  it('elapsed extrapoliert mit 1-Hz-Forecast', () => {
    const clock = useSimClock('sim-clock')
    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:00:00.000Z' }))
    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:00:30.000Z' }))

    // baseSec = 30, forecast = 0 (frame just received)
    expect(clock.elapsed.value).toBeGreaterThanOrEqual(30)
    expect(clock.elapsed.value).toBeLessThan(31)

    // Advance Wallclock 2 s → forecast = 2
    vi.advanceTimersByTime(2_000)
    const after = clock.elapsed.value
    expect(after).toBeGreaterThanOrEqual(32)
    expect(after).toBeLessThan(33)
  })

  it('stop() resettet State und gibt Interval frei', () => {
    const clock = useSimClock('sim-clock')
    clock.ingest(makeEvent({ sim_time: '2026-05-16T10:00:00.000Z' }))
    expect(clock.currentSimTime.value).not.toBeNull()

    clock.stop()
    expect(clock.currentSimTime.value).toBeNull()
    expect(clock.start.value).toBeNull()
    expect(clock.elapsed.value).toBe(0)
  })
})
