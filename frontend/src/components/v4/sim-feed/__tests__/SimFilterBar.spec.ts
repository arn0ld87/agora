/**
 * SimFilterBar — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.2.
 * Deckt: alle Selects haben Labels, Freitext ist scope-abhaengig sichtbar,
 * leere Personas-Liste deaktiviert das Feld mit Hilfetext, und jede
 * Aenderung emittiert das passende update:*-Event.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimFilterBar from '../SimFilterBar.vue'

function baseProps() {
  return {
    platform: 'all' as const,
    round: null,
    persona: null,
    q: '',
    personas: [{ id: 'alice', name: 'Alice' }],
    rounds: [0, 1, 2],
    scope: 'feed' as const,
  }
}

describe('SimFilterBar', () => {
  it('rendert Platform-, Runden- und Persona-Select mit Label', () => {
    const w = mount(SimFilterBar, { props: baseProps() })
    expect(w.find('label[for^="sfb-platform-"]').exists()).toBe(true)
    expect(w.find('label[for^="sfb-round-"]').exists()).toBe(true)
    expect(w.find('label[for^="sfb-persona-"]').exists()).toBe(true)
  })

  it('scope=feed zeigt das Suchfeld mit role=searchbox', () => {
    const w = mount(SimFilterBar, { props: baseProps() })
    expect(w.find('[role="searchbox"]').exists()).toBe(true)
  })

  it('scope=rounds blendet das Suchfeld aus (nur Feed/Diskurs, §1)', () => {
    const w = mount(SimFilterBar, { props: { ...baseProps(), scope: 'rounds' } })
    expect(w.find('[role="searchbox"]').exists()).toBe(false)
  })

  it('leere Personas-Liste deaktiviert das Select und zeigt den Hilfetext', () => {
    const w = mount(SimFilterBar, { props: { ...baseProps(), personas: [] } })
    const select = w.find('select#sfb-persona-feed')
    expect((select.element as HTMLSelectElement).disabled).toBe(true)
    expect(w.text()).toContain('feed.scope.noPersonas')
  })

  it('Plattform-Wechsel emittiert update:platform', async () => {
    const w = mount(SimFilterBar, { props: baseProps() })
    await w.get('#sfb-platform-feed').setValue('reddit')
    expect(w.emitted('update:platform')?.[0]).toEqual(['reddit'])
  })

  it('Runden-Wechsel emittiert update:round als Zahl, leere Auswahl als null', async () => {
    const w = mount(SimFilterBar, { props: baseProps() })
    await w.get('#sfb-round-feed').setValue('2')
    expect(w.emitted('update:round')?.[0]).toEqual([2])
    await w.get('#sfb-round-feed').setValue('')
    expect(w.emitted('update:round')?.[1]).toEqual([null])
  })

  it('Freitext-Eingabe emittiert update:q', async () => {
    const w = mount(SimFilterBar, { props: baseProps() })
    await w.get('[role="searchbox"]').setValue('reise')
    expect(w.emitted('update:q')?.[0]).toEqual(['reise'])
  })

  it('loading=true deaktiviert alle Selects', () => {
    const w = mount(SimFilterBar, { props: { ...baseProps(), loading: true } })
    for (const el of w.findAll('select')) {
      expect((el.element as HTMLSelectElement).disabled).toBe(true)
    }
  })
})
