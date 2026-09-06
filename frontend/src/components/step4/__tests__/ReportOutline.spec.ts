/**
 * ReportOutline — PR 6 (Premium-Redesign, "Bericht lesen").
 *
 * Prueft: Sprungmarken werden aus outline.sections abgeleitet (Summary +
 * N Abschnitte), Klick emittiert `navigate` mit der Anker-ID, aktiver
 * Eintrag traegt `aria-selected="true"`, Anhang-Zaehler werden gerendert.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportOutline from '../ReportOutline.vue'
import { ReportReaderTestId } from '../../../contracts/testIds'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      step4: {
        reader: {
          outlineTitle: 'Bericht',
          outlineSectionsCount: '{count} Abschnitte',
          appendixTitle: 'Anhang',
          appendixHypotheses: '{count} Hypothesen',
          appendixDataGaps: '{count} Datenlücken',
          appendixEvidence: '{count} Belege',
          appendixRedTeam: '{count} Red-Team-Befunde',
        },
      },
    },
  },
})

function mountOutline(activeId = 'summary') {
  return mount(ReportOutline, {
    props: {
      items: [
        { id: 'summary', num: '0', label: 'Zusammenfassung' },
        { id: 'section-1', num: '1', label: 'Ausgangslage' },
        { id: 'section-2', num: '2', label: 'Stakeholder' },
      ],
      activeId,
      sectionsCount: 2,
      hypothesesCount: 3,
      dataGapsCount: 1,
      evidenceCount: 12,
      redTeamCount: 2,
    },
    global: { plugins: [i18n] },
  })
}

describe('ReportOutline', () => {
  it('rendert alle Outline-Eintraege als role=tab', () => {
    const wrapper = mountOutline()
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs).toHaveLength(3)
  })

  it('markiert den aktiven Eintrag ueber aria-selected in einem echten tablist', () => {
    const wrapper = mountOutline('section-1')
    expect(wrapper.find('[role="tablist"]').exists()).toBe(true)
    const items = wrapper.findAll(`[data-testid="${ReportReaderTestId.outlineItem}"]`)
    expect(items[1].attributes('aria-selected')).toBe('true')
    expect(items[0].attributes('aria-selected')).toBe('false')
  })

  it('emittiert navigate mit der Anker-ID beim Klick', async () => {
    const wrapper = mountOutline()
    const items = wrapper.findAll(`[data-testid="${ReportReaderTestId.outlineItem}"]`)
    await items[2].trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['section-2']])
  })

  it('rendert die Anhang-Zaehler (Hypothesen, Datenluecken, Belege, Red-Team)', () => {
    const wrapper = mountOutline()
    expect(wrapper.text()).toContain('3 Hypothesen')
    expect(wrapper.text()).toContain('1 Datenlücken')
    expect(wrapper.text()).toContain('12 Belege')
    expect(wrapper.text()).toContain('2 Red-Team-Befunde')
  })
})
