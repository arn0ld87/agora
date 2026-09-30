/**
 * Platzhalter-Views der neuen Kind-Routen (Slice UI-2b, Commit 2).
 * SimActionsView wird erst in Commit 5 durch die echte Komponente ersetzt
 * (§2.10 der Spezifikation); dieser Test pinnt nur den konsistenten
 * Empty-State-Vertrag (role="status" + uebersetzter Text), damit ein
 * Redirect/eine Route nie auf eine leere, unbeschriftete Seite fuehrt.
 *
 * SimThreadsView/SimThreadFocusView/SimRoundsView sind keine Platzhalter
 * mehr — ihre Tests leben in den jeweils eigenen *.spec.ts-Dateien.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimActionsView from '../SimActionsView.vue'

describe('Platzhalter-Views (Slice UI-2b, Commit 2)', () => {
  it('SimActionsView zeigt role=status mit Placeholder-Key', () => {
    const w = mount(SimActionsView)
    expect(w.get('[role="status"]').text()).toBe('feed.actionsPlaceholder')
  })
})
