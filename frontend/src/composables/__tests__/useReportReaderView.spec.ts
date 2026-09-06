/**
 * buildReportReaderView — PR 6 (Premium-Redesign, "Bericht lesen").
 *
 * Der Kern dieses Moduls ist eine Kopplung: die Outline und das Abschnitts-HTML
 * duerfen nicht auseinanderlaufen, weil ReportReader Abschnitt i aus
 * `sectionHtml[i]` rendert. Die Tests pruefen genau diese Kopplung.
 */
import { describe, it, expect } from 'vitest'
import { buildReportReaderView } from '../useReportReaderView'
import type { ReportOutline, ReportSection } from '@/contracts/reportContract'

const FALLBACK_TITLE = 'Bericht'
const FULL_REPORT_LABEL = 'Vollständiger Bericht'

const outline: ReportOutline = {
  title: 'Nexora Triage Assist',
  summary: 'Sechs Stakeholdergruppen erwarten Entlastung.',
  sections: [
    { title: 'Ausgangslage', description: 'x' },
    { title: 'Stakeholder', description: 'y' },
    { title: 'Empfehlung', description: 'z' },
  ],
}

function mkEvidenceSection(index: number, title: string): ReportSection {
  return {
    section_index: index,
    section_title: title,
    section_summary: `Zusammenfassung ${index}`,
    claims: [],
    hypotheses: [],
    hypotheses_appendix: [],
    data_gaps: [],
    structured_metadata: {},
    generation_failed: false,
    unbound_evidence_refs: [],
    unverified_statements: [],
  } as unknown as ReportSection
}

function build(overrides: Partial<Parameters<typeof buildReportReaderView>[0]> = {}) {
  return buildReportReaderView({
    outline: null,
    sectionHtml: {},
    reportHtml: '<p>Ganzer Bericht</p>',
    evidenceSections: [],
    fallbackTitle: FALLBACK_TITLE,
    fullReportLabel: FULL_REPORT_LABEL,
    ...overrides,
  })
}

describe('buildReportReaderView', () => {
  it('reicht echte Outline und echtes Abschnitts-HTML unveraendert durch', () => {
    const sectionHtml = { 1: '<p>eins</p>', 2: '<p>zwei</p>', 3: '<p>drei</p>' }
    const view = build({ outline, sectionHtml })
    expect(view.outline).toBe(outline)
    expect(view.sectionHtml).toBe(sectionHtml)
  })

  it('leitet die Outline aus der Evidenzkarte ab, wenn keine Outline vorliegt', () => {
    const view = build({
      sectionHtml: { 1: '<p>eins</p>', 2: '<p>zwei</p>' },
      evidenceSections: [mkEvidenceSection(1, 'Ausgangslage'), mkEvidenceSection(2, 'Stakeholder')],
    })
    expect(view.outline.sections.map((s) => s.title)).toEqual(['Ausgangslage', 'Stakeholder'])
    expect(view.outline.title).toBe(FALLBACK_TITLE)
  })

  it('Regression: ohne Abschnitts-HTML bleibt genau ein Abschnitt uebrig — kein leerer Rest', () => {
    // Persistierte Berichte (`_status_from_persisted_report`) liefern den
    // Bericht als Ganzes, aber keine `generated_sections`. Frueher waehlten
    // Outline und HTML ihren Fallback unabhaengig: die Outline kam aus der
    // Evidenzkarte mit N Abschnitten, das HTML bestand aus einem Block — jeder
    // Abschnitt ausser dem ersten blieb leer.
    const view = build({
      sectionHtml: {},
      evidenceSections: [
        mkEvidenceSection(1, 'Ausgangslage'),
        mkEvidenceSection(2, 'Stakeholder'),
        mkEvidenceSection(3, 'Empfehlung'),
      ],
    })
    expect(view.outline.sections).toHaveLength(1)
    expect(view.outline.sections[0].title).toBe(FULL_REPORT_LABEL)
    expect(view.sectionHtml).toEqual({ 1: '<p>Ganzer Bericht</p>' })
  })

  it('Regression: dieselbe Kopplung gilt, wenn eine echte Outline ohne Abschnitts-HTML vorliegt', () => {
    const view = build({ outline, sectionHtml: {} })
    expect(view.outline.sections).toHaveLength(1)
    // Titel und Zusammenfassung der echten Outline gehen dabei nicht verloren.
    expect(view.outline.title).toBe(outline.title)
    expect(view.outline.summary).toBe(outline.summary)
    expect(view.sectionHtml).toEqual({ 1: '<p>Ganzer Bericht</p>' })
  })

  it('jeder Outline-Abschnitt hat immer ein HTML-Gegenstueck', () => {
    // Invariante statt Einzelfall: fuer jede Eingabekombination muss zu jedem
    // Abschnitt i ein `sectionHtml[i]` existieren.
    const faelle: Array<Partial<Parameters<typeof buildReportReaderView>[0]>> = [
      { outline, sectionHtml: { 1: 'a', 2: 'b', 3: 'c' } },
      { outline: null, sectionHtml: { 1: 'a' }, evidenceSections: [mkEvidenceSection(1, 'A')] },
      { outline, sectionHtml: {} },
      { outline: null, sectionHtml: {}, evidenceSections: [mkEvidenceSection(1, 'A'), mkEvidenceSection(2, 'B')] },
      { outline: null, sectionHtml: {} },
    ]
    for (const fall of faelle) {
      const view = build(fall)
      view.outline.sections.forEach((_, idx) => {
        expect(view.sectionHtml[String(idx + 1)]).toBeTruthy()
      })
    }
  })
})
