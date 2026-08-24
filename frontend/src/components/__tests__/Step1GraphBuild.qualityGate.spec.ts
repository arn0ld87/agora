import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

/**
 * Issue #1029, Befund B-24 — „bereit“ ist eine Aussage über das Ergebnis,
 * nicht über den Programmablauf.
 *
 * Ein Graph mit 3 Entitäten und 0 Beziehungen hat den Build überstanden.
 * Bis hierher meldete Karte 3 trotzdem „Bereit“ und gab den Weiter-Knopf
 * frei; der Report scheiterte Minuten später an fehlender Evidenz.
 */

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../../api/simulation', () => ({ createSimulation: vi.fn() }))

import Step1GraphBuild from '../Step1GraphBuild.vue'

function mountStep(qualityBlocked: boolean, currentPhase = 2) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  return mount(Step1GraphBuild, {
    props: {
      currentPhase,
      qualityBlocked,
      projectData: { project_id: 'p1', graph_id: 'g1' },
      graphData: { node_count: 3, edge_count: 0, nodes: [], edges: [] },
      systemLogs: [],
    },
    global: {
      plugins: [i18n],
      stubs: {
        Kicker: { template: '<span><slot /></span>' },
        Badge: { template: '<span class="badge"><slot /></span>' },
        Button: {
          props: ['disabled', 'loading', 'variant', 'arrow'],
          template: '<button :disabled="disabled"><slot /></button>',
        },
      },
    },
  })
}

/** Karte 3 ist die „Weiter“-Karte; ihr Button führt in den Folgeschritt. */
function nextButton(wrapper: ReturnType<typeof mountStep>) {
  const buttons = wrapper.findAll('button')
  return buttons[buttons.length - 1]
}

describe('Step1GraphBuild — Qualitätsgate', () => {
  it('meldet einen sauberen Build als bereit', () => {
    const wrapper = mountStep(false)
    expect(wrapper.text()).toContain('Bereit')
    expect(nextButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('meldet einen unzureichenden Graphen nicht als bereit', () => {
    const wrapper = mountStep(true)
    expect(wrapper.text()).toContain('Unzureichend')
    expect(wrapper.text()).not.toContain('Bereit')
  })

  it('sperrt den Weiter-Knopf bei unzureichendem Graphen', () => {
    expect(nextButton(mountStep(true)).attributes('disabled')).toBeDefined()
  })

  it('nennt den Grund statt „Graph fertig.“', () => {
    const wrapper = mountStep(true)
    expect(wrapper.text()).toContain('erfüllt die Qualitätsschwelle nicht')
    expect(wrapper.text()).not.toContain('Graph fertig.')
  })

  it('sperrt weiterhin, solange der Build läuft', () => {
    expect(nextButton(mountStep(false, 1)).attributes('disabled')).toBeDefined()
  })
})
