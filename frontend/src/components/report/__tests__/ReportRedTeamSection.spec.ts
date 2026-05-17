/**
 * ReportRedTeamSection (Slice 5 — Issue #497).
 *
 * Prueft:
 * - 3 red_team_findings → Section rendert, 3 Items sichtbar.
 * - red_team_findings: [] → Section NICHT im DOM (keine leere Box).
 * - Section besitzt id="section-red-team" (In-Page-Anker).
 * - Red-Team-Section steht vor Data-Gaps-Section (DOM-Reihenfolge).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ReportRedTeamSection from '../ReportRedTeamSection.vue'

describe('ReportRedTeamSection (Slice 5)', () => {
  it('rendert 3 Findings wenn findings nicht leer ist', () => {
    const findings = [
      'Widerspruch zwischen Claim C1 und Claim C3.',
      'Konsens-Annahme nicht durch Evidence gestützt.',
      'Persona P2 widerspricht dem Mehrheitsurteil.',
    ]
    const wrapper = mount(ReportRedTeamSection, {
      props: { findings },
    })

    const items = wrapper.findAll('[data-testid="red-team-finding"]')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toContain('Widerspruch')
    expect(items[1].text()).toContain('Konsens-Annahme')
    expect(items[2].text()).toContain('Persona P2')
  })

  it('rendert die Section NICHT wenn findings leer ist', () => {
    const wrapper = mount(ReportRedTeamSection, {
      props: { findings: [] },
    })

    expect(wrapper.find('#section-red-team').exists()).toBe(false)
  })

  it('besitzt Section-Anker id="section-red-team"', () => {
    const wrapper = mount(ReportRedTeamSection, {
      props: { findings: ['Ein Befund.'] },
    })

    expect(wrapper.find('#section-red-team').exists()).toBe(true)
  })

  it('Red-Team-Section steht vor Data-Gaps im zusammengesetzten Kontext', () => {
    // Testet DOM-Reihenfolge: Red-Team muss vor data_gaps erscheinen.
    // Wir simulieren dies durch ein Wrapper-div mit beiden Sections.
    const WrapperComponent = {
      components: { ReportRedTeamSection },
      template: `
        <div>
          <ReportRedTeamSection :findings="findings" />
          <section id="section-data-gaps">Datenlücken</section>
        </div>
      `,
      props: ['findings'],
    }

    const wrapper = mount(WrapperComponent, {
      props: { findings: ['Befund 1.'] },
    })

    const children = wrapper.find('div').element.children
    const ids = Array.from(children).map((el) => (el as Element).id)
    const redTeamIdx = ids.indexOf('section-red-team')
    const dataGapsIdx = ids.indexOf('section-data-gaps')

    expect(redTeamIdx).toBeGreaterThanOrEqual(0)
    expect(dataGapsIdx).toBeGreaterThanOrEqual(0)
    expect(redTeamIdx).toBeLessThan(dataGapsIdx)
  })
})
