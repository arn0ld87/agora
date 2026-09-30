/**
 * Platzhalter-Views der neuen Kind-Routen (Slice UI-2b, Commit 2).
 * SimThreadsView/SimThreadFocusView/SimRoundsView/SimActionsView werden in
 * spaeteren Commits durch die echten Komponenten ersetzt (§2.7-§2.10 der
 * Spezifikation); dieser Test pinnt nur den konsistenten Empty-State-Vertrag
 * (role="status" + uebersetzter Text), damit ein Redirect/eine Route nie auf
 * eine leere, unbeschriftete Seite fuehrt.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimThreadsView from '../SimThreadsView.vue'
import SimThreadFocusView from '../SimThreadFocusView.vue'
import SimRoundsView from '../SimRoundsView.vue'
import SimActionsView from '../SimActionsView.vue'

describe('Platzhalter-Views (Slice UI-2b, Commit 2)', () => {
  it('SimThreadsView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimThreadsView)
    expect(w.get('[role="status"]').text()).toBe('feed.threadsPlaceholder')
  })

  it('SimThreadFocusView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimThreadFocusView, { props: { postId: 'post_1' } })
    expect(w.get('[role="status"]').text()).toBe('feed.threadFocusPlaceholder')
  })

  it('SimRoundsView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimRoundsView)
    expect(w.get('[role="status"]').text()).toBe('feed.roundsPlaceholder')
  })

  it('SimActionsView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimActionsView)
    expect(w.get('[role="status"]').text()).toBe('feed.actionsPlaceholder')
  })
})
