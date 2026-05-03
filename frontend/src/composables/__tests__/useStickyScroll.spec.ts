// Issue #130 / SUB1 — Sticky-Scroll-Composable.
//
// Verträge:
//  1. Wenn Nutzer am Ende: `markAppended` scrollt automatisch ans Ende, Counter bleibt 0.
//  2. Wenn Nutzer hochgescrollt hat: `markAppended` erhöht den Counter, kein Scroll-Hijack.
//  3. `scrollToBottom()` springt synchron ans Ende und reset den Counter.
//  4. Scroll-Listener ist via rAF gedrosselt; Eval läuft erst im nächsten Frame.

import { describe, it, expect, beforeEach } from 'vitest'
import { ref, nextTick, type Ref } from 'vue'

import { useStickyScroll } from '../useStickyScroll'

function makeContainer(
  { scrollHeight = 1000, clientHeight = 200, scrollTop = 800 }: { scrollHeight?: number; clientHeight?: number; scrollTop?: number } = {}
): HTMLElement {
  // JSDOM exposes scrollTop als beschreibbares Number-Field. scrollHeight und
  // clientHeight defaulten auf 0; wir patchen sie über Object.defineProperty.
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', {
    configurable: true,
    get: () => scrollHeight,
  })
  Object.defineProperty(el, 'clientHeight', {
    configurable: true,
    get: () => clientHeight,
  })
  el.scrollTop = scrollTop
  return el
}

// `requestAnimationFrame` ist im Composable gegen einen Fallback abgesichert.
// Im Test warten wir explizit auf den nächsten Frame, damit rAF-Callbacks abgearbeitet sind.
function nextFrame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => resolve())
    } else {
      setTimeout(resolve, 20)
    }
  })
}

describe('useStickyScroll', () => {
  let containerRef: Ref<HTMLElement | null>

  beforeEach(() => {
    containerRef = ref<HTMLElement | null>(null)
  })

  it('markAppended scrollt ans Ende, wenn Nutzer am Ende ist', async () => {
    const el = makeContainer({ scrollHeight: 1000, clientHeight: 200, scrollTop: 800 })
    containerRef.value = el
    const sticky = useStickyScroll(containerRef)
    await nextTick()

    sticky.markAppended(3)

    expect(el.scrollTop).toBe(1000)
    expect(sticky.unreadCount.value).toBe(0)
    expect(sticky.autoScrollEnabled.value).toBe(true)
  })

  it('erhöht den Counter, wenn Nutzer hochgescrollt hat', async () => {
    const el = makeContainer({ scrollHeight: 1000, clientHeight: 200, scrollTop: 100 })
    containerRef.value = el
    const sticky = useStickyScroll(containerRef)
    await nextTick()

    // Initial-Eval beim Attach hat schon `autoScrollEnabled=false` gesetzt
    // (distance > 32). Trotzdem stoßen wir explizit eine Scroll-Eval an,
    // damit das Verhalten dem Live-Pfad entspricht.
    el.dispatchEvent(new Event('scroll'))
    await nextFrame()

    sticky.markAppended(2)
    sticky.markAppended(1)

    expect(el.scrollTop).toBe(100) // unverändert, kein Hijack
    expect(sticky.unreadCount.value).toBe(3)
    expect(sticky.autoScrollEnabled.value).toBe(false)
  })

  it('scrollToBottom springt synchron ans Ende und reset Counter', async () => {
    const el = makeContainer({ scrollHeight: 1000, clientHeight: 200, scrollTop: 100 })
    containerRef.value = el
    const sticky = useStickyScroll(containerRef)
    await nextTick()
    el.dispatchEvent(new Event('scroll'))
    await nextFrame()
    sticky.markAppended(5)

    sticky.scrollToBottom()

    expect(el.scrollTop).toBe(1000)
    expect(sticky.unreadCount.value).toBe(0)
    expect(sticky.autoScrollEnabled.value).toBe(true)
  })

  it('reagiert auf Scroll-Events und schaltet Auto-Scroll wieder an, wenn Nutzer ans Ende scrollt', async () => {
    const el = makeContainer({ scrollHeight: 1000, clientHeight: 200, scrollTop: 100 })
    containerRef.value = el
    const sticky = useStickyScroll(containerRef)
    await nextTick()

    el.dispatchEvent(new Event('scroll'))
    await nextFrame()
    expect(sticky.autoScrollEnabled.value).toBe(false)

    el.scrollTop = 800
    el.dispatchEvent(new Event('scroll'))
    await nextFrame()
    expect(sticky.autoScrollEnabled.value).toBe(true)
    expect(sticky.unreadCount.value).toBe(0)
  })

  it('verträgt einen leeren Container-Ref', () => {
    const sticky = useStickyScroll(containerRef)
    expect(() => sticky.markAppended(1)).not.toThrow()
    expect(() => sticky.scrollToBottom()).not.toThrow()
    expect(sticky.unreadCount.value).toBe(0)
  })
})
