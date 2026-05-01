// Issue #130 / SUB1 — Sticky-Scroll-Composable.
//
// Verträge:
//  1. Wenn Nutzer am Ende: `markAppended` scrollt automatisch ans Ende, Counter bleibt 0.
//  2. Wenn Nutzer hochgescrollt hat: `markAppended` erhöht den Counter, kein Scroll-Hijack.
//  3. `scrollToBottom()` springt synchron ans Ende und reset den Counter.

import { describe, it, expect, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

import { useStickyScroll } from '../useStickyScroll'

function makeContainer({ scrollHeight = 1000, clientHeight = 200, scrollTop = 800 } = {}) {
  // JSDOM exposes scrollTop/scrollHeight/clientHeight as plain props on Element.
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', {
    configurable: true,
    get: () => scrollHeight,
  })
  Object.defineProperty(el, 'clientHeight', {
    configurable: true,
    get: () => clientHeight,
  })
  // scrollTop ist normal beschreibbar in JSDOM.
  el.scrollTop = scrollTop
  return el
}

describe('useStickyScroll', () => {
  let containerRef

  beforeEach(() => {
    containerRef = ref(null)
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

    // Listener anstoßen, weil scrollTop initial schon hoch war.
    el.dispatchEvent(new Event('scroll'))

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
    sticky.markAppended(5)

    sticky.scrollToBottom()

    expect(el.scrollTop).toBe(1000)
    expect(sticky.unreadCount.value).toBe(0)
    expect(sticky.autoScrollEnabled.value).toBe(true)
  })

  it('reagiert auf Scroll-Events und schaltet Auto-Scroll wieder an, wenn Nutzer ans Ende scrollt', async () => {
    let st = 100
    const el = makeContainer({ scrollHeight: 1000, clientHeight: 200, scrollTop: st })
    Object.defineProperty(el, 'scrollTop', {
      configurable: true,
      get: () => st,
      set: (v) => { st = v },
    })
    containerRef.value = el
    const sticky = useStickyScroll(containerRef)
    await nextTick()

    el.dispatchEvent(new Event('scroll'))
    expect(sticky.autoScrollEnabled.value).toBe(false)

    st = 800 // user scrolled back to bottom
    el.dispatchEvent(new Event('scroll'))
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
