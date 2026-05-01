/**
 * useStickyScroll — Sticky-Scroll für Live-Feeds und Log-Pane.
 *
 * Issue #130: heute hijacked der Live-Feed jeden User, der nach oben
 * scrollt (`scrollTop = scrollHeight` nach jedem Append). Composable
 * kapselt das richtige Verhalten:
 *
 *   1. Konsument hängt `containerRef` an sein scrollbares Element.
 *   2. Konsument ruft `markAppended(deltaCount)` nach jedem Push.
 *   3. Wenn der Nutzer am Ende klebt (innerhalb `BOTTOM_THRESHOLD_PX`),
 *      scrollt das Composable selbst ans Ende.
 *   4. Sonst zählt es ungesehene Einträge in `unreadCount` hoch — der
 *      Konsument zeigt einen Banner, dessen Klick `scrollToBottom()`
 *      auslöst (springt ans Ende, reset Counter, AutoScroll wieder an).
 *
 * Nicht-Ziel: Smooth-Scroll-Animation (lassen wir dem Browser-Default).
 */

import { ref, watch, onUnmounted } from 'vue'

const BOTTOM_THRESHOLD_PX = 32

/**
 * @param {import('vue').Ref<HTMLElement|null>} containerRef
 * @returns {{
 *   isAtBottom: import('vue').Ref<boolean>,
 *   unreadCount: import('vue').Ref<number>,
 *   autoScrollEnabled: import('vue').Ref<boolean>,
 *   markAppended: (delta?: number) => void,
 *   scrollToBottom: () => void,
 *   evaluatePosition: () => void,
 * }}
 */
export function useStickyScroll(containerRef) {
  const isAtBottom = ref(true)
  const autoScrollEnabled = ref(true)
  const unreadCount = ref(0)

  let _detach = null

  function evaluatePosition() {
    const el = containerRef.value
    if (!el) return
    // distance from bottom in pixels
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    const atBottom = distance <= BOTTOM_THRESHOLD_PX
    isAtBottom.value = atBottom
    autoScrollEnabled.value = atBottom
    if (atBottom) {
      unreadCount.value = 0
    }
  }

  function scrollToBottom() {
    const el = containerRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
    isAtBottom.value = true
    autoScrollEnabled.value = true
    unreadCount.value = 0
  }

  function markAppended(delta = 1) {
    const el = containerRef.value
    if (!el) {
      // Container noch nicht gemountet → Append zählt nicht als „verloren";
      // beim Mount springt die Eval auf isAtBottom=true und alles ist gut.
      return
    }
    if (autoScrollEnabled.value) {
      // synchron — der Push liegt schon im DOM (caller ruft markAppended
      // im Anschluss an seinen Push, evtl. nach `nextTick`).
      el.scrollTop = el.scrollHeight
      unreadCount.value = 0
    } else {
      const safeDelta = Number.isFinite(delta) && delta > 0 ? delta : 1
      unreadCount.value += safeDelta
    }
  }

  function attach(el) {
    if (!el) return
    let ticking = false
    const handler = () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          evaluatePosition()
          ticking = false
        })
        ticking = true
      }
    }
    el.addEventListener('scroll', handler, { passive: true })
    _detach = () => el.removeEventListener('scroll', handler)
    // Initialer State: wir starten am Ende (= AutoScroll an).
    evaluatePosition()
  }

  function detach() {
    if (_detach) {
      _detach()
      _detach = null
    }
  }

  // Container-Ref kann sich nachträglich auf ein DOM-Element setzen.
  watch(containerRef, (el, oldEl) => {
    if (oldEl) detach()
    if (el) attach(el)
  }, { immediate: true })

  onUnmounted(detach)

  return {
    isAtBottom,
    unreadCount,
    autoScrollEnabled,
    markAppended,
    scrollToBottom,
    evaluatePosition,
  }
}
