/**
 * GraphToolbar — Issue #1023 (Befund B-08).
 *
 * toggle-maximize emittierte seit jeher ins Leere (kein Listener an der
 * einzigen Konsument-Stelle StepGraphBuildView.vue), ebenso refresh und
 * close-graph. refresh/toggle-maximize sind jetzt verdrahtet (siehe
 * StepGraphBuildView.spec.ts) — der Maximize-Button zeigt dafuer eine
 * i18n'te, zustandsabhaengige Beschriftung statt des frueheren
 * hartkodierten title="Maximize/Restore". close-graph hatte an der
 * einzigen Konsument-Stelle keinen sinnvollen Wiederherstellungs-Pfad
 * (die Sektion ist v-if="graphData", ein "Schliessen" ohne Wieder-Oeffnen
 * waere irrefuehrend) und wurde deshalb entfernt statt verdrahtet.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import GraphToolbar from '../GraphToolbar.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      common: { refresh: 'Aktualisieren' },
      graph: {
        panel: 'Graph',
        ui: {
          maximizeLayout: 'Vergrößern',
          restoreLayout: 'Verkleinern',
        },
      },
    },
  },
})

function mountToolbar(props: Record<string, unknown> = {}) {
  return mount(GraphToolbar, {
    props,
    global: { plugins: [i18n] },
  })
}

describe('GraphToolbar (Issue #1023, Befund B-08)', () => {
  it('rendert keinen close-graph-Button mehr (kein sinnvoller Wiederherstellungs-Pfad)', () => {
    const w = mountToolbar()
    expect(w.find('.icon-close').exists()).toBe(false)
  })

  it('Maximize-Button zeigt den i18n-Key fuer "maximieren", wenn isMaximized=false', () => {
    const w = mountToolbar({ isMaximized: false })
    const btn = w.find('.icon-maximize').element.closest('button')
    expect(btn?.getAttribute('title')).toBe('Vergrößern')
    expect(btn?.getAttribute('aria-pressed')).toBe('false')
  })

  it('Maximize-Button zeigt den i18n-Key fuer "verkleinern", wenn isMaximized=true', () => {
    const w = mountToolbar({ isMaximized: true })
    const btn = w.find('.icon-maximize').element.closest('button')
    expect(btn?.getAttribute('title')).toBe('Verkleinern')
    expect(btn?.getAttribute('aria-pressed')).toBe('true')
  })

  it('emittiert toggle-maximize bei Klick', async () => {
    const w = mountToolbar()
    const btn = w.find('.icon-maximize').element.closest('button')
    await btn?.dispatchEvent(new Event('click'))
    expect(w.emitted('toggle-maximize')).toBeTruthy()
  })
})
