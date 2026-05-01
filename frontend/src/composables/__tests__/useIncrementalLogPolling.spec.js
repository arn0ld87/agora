// Issue #131 / SUB1 — Sticky-Scroll-Bridge im inkrementellen Log-Polling.
//
// Verträge:
//  1. Ohne `stickyScroll` bleibt das alte Verhalten: nach Append wird der
//     Container blind ans Ende gescrollt.
//  2. Mit `stickyScroll` ruft das Composable `markAppended(deltaCount)`
//     statt `el.scrollTop = el.scrollHeight`.
//  3. `appendedCount` zählt nur tatsächlich angehängte Lines (parseLine null → skip).

import { describe, it, expect, vi } from 'vitest'
import { nextTick } from 'vue'

import { useIncrementalLogPolling } from '../useIncrementalLogPolling'

function makeFakeContainer() {
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', { configurable: true, get: () => 1000 })
  Object.defineProperty(el, 'clientHeight', { configurable: true, get: () => 200 })
  el.scrollTop = 0
  return el
}

describe('useIncrementalLogPolling', () => {
  it('scrollt ans Ende, wenn keine sticky-Instanz übergeben wurde', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      success: true,
      data: { lines: ['a', 'b', 'c'], next_line: 3 },
    })
    const polling = useIncrementalLogPolling({ fetcher })
    const el = makeFakeContainer()
    polling.containerRef.value = el

    await polling.tick()
    await nextTick()

    expect(polling.lines.value).toEqual(['a', 'b', 'c'])
    expect(el.scrollTop).toBe(1000)
  })

  it('ruft stickyScroll.markAppended statt blind zu scrollen', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      success: true,
      data: { lines: ['a', 'b'], next_line: 2 },
    })
    const stickyScroll = { markAppended: vi.fn() }
    const polling = useIncrementalLogPolling({ fetcher, stickyScroll })
    const el = makeFakeContainer()
    polling.containerRef.value = el

    await polling.tick()
    await nextTick()

    expect(polling.lines.value).toEqual(['a', 'b'])
    expect(stickyScroll.markAppended).toHaveBeenCalledWith(2)
    expect(el.scrollTop).toBe(0) // kein Hijack
  })

  it('zählt nur tatsächlich angehängte Lines (parseLine null = skip)', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      success: true,
      data: { lines: ['keep', 'skip', 'keep'], next_line: 3 },
    })
    const stickyScroll = { markAppended: vi.fn() }
    const parseLine = (raw) => raw === 'skip' ? null : raw
    const polling = useIncrementalLogPolling({ fetcher, parseLine, stickyScroll })
    const el = makeFakeContainer()
    polling.containerRef.value = el

    await polling.tick()
    await nextTick()

    expect(polling.lines.value).toEqual(['keep', 'keep'])
    expect(stickyScroll.markAppended).toHaveBeenCalledWith(2)
  })

  it('ruft markAppended NICHT, wenn keine neuen Lines kamen', async () => {
    const fetcher = vi.fn().mockResolvedValue({
      success: true,
      data: { lines: [], next_line: 0 },
    })
    const stickyScroll = { markAppended: vi.fn() }
    const polling = useIncrementalLogPolling({ fetcher, stickyScroll })

    await polling.tick()

    expect(stickyScroll.markAppended).not.toHaveBeenCalled()
  })
})
