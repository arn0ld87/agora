/**
 * Platzhalter-Views der neuen Kind-Routen (Slice UI-2b, Commit 2).
 * SimRoundsView/SimActionsView werden erst in Commit 4/5 durch die echten
 * Komponenten ersetzt (§2.9-§2.10 der Spezifikation); dieser Test pinnt nur
 * den konsistenten Empty-State-Vertrag (role="status" + uebersetzter Text),
 * damit ein Redirect/eine Route nie auf eine leere, unbeschriftete Seite
 * fuehrt.
 *
 * SimThreadsView/SimThreadFocusView sind seit Commit 4 keine Platzhalter
 * mehr — ihre Tests leben in SimThreadsView.spec.ts / SimThreadFocusView.spec.ts.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimRoundsView from '../SimRoundsView.vue'
import SimActionsView from '../SimActionsView.vue'

describe('Platzhalter-Views (Slice UI-2b, Commit 2)', () => {
  it('SimRoundsView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimRoundsView)
    expect(w.get('[role="status"]').text()).toBe('feed.roundsPlaceholder')
  })

  it('SimActionsView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimActionsView)
    expect(w.get('[role="status"]').text()).toBe('feed.actionsPlaceholder')
  })
})
