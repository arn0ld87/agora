/**
 * ReportEvidenceRail — PR 6 (Premium-Redesign, "Bericht lesen").
 *
 * Prueft: Claims der aktiven Section zeigen ein Confidence-Wort (Audit-Fix:
 * "Confidence als Prozentzahl ohne Erklaerung" darf nicht wiederkehren),
 * gebundene Belege und Datenluecken werden gerendert, Red-Team-Befunde
 * erscheinen im eigenen Block, Klick auf einen Beleg-Anker emittiert
 * `navigate`.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportEvidenceRail from '../ReportEvidenceRail.vue'
import { ReportReaderTestId } from '../../../contracts/testIds'
import type { EvidenceIndex, ReportSection } from '../../../contracts/reportContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      step4: {
        quote: { openSource: 'Quelle öffnen' },
        reader: {
          railTitle: 'Aussagen in Abschnitt {num}',
          railEvidenceTitle: 'Belege an dieser Stelle',
          railGapsTitle: 'Datenlücken in diesem Abschnitt',
          railRedTeamTitle: 'Red-Team zu Abschnitt {num}',
          railEmpty: 'Keine Aussagen für diesen Abschnitt erfasst.',
          confidence: {
            speculative: 'spekulativ',
            low: 'niedrig',
            medium: 'mittel',
            high: 'hoch',
            verified: 'verifiziert',
          },
        },
      },
    },
  },
})

const evidenceIndex: EvidenceIndex = {
  ev_1: {
    evidence_id: 'ev_1',
    producer_key: 'report_generation',
    type: 'agent_interview',
    source: 'Pflegeteam Station 3',
    snippet: 'Zeitersparnis ist eine Zahl aus der Präsentation.',
    quote: 'Zeitersparnis ist eine Zahl aus der Präsentation.',
    source_id_anchor: 'agent-log:entry-42',
    source_kind: 'agent_quote',
    persona_stakeholder_group: 'Pflege',
  } as unknown as EvidenceIndex[string],
}

const section: ReportSection = {
  section_index: 3,
  section_title: 'Entlastungswirkung im Betrieb',
  section_summary: 'x',
  claims: [
    {
      claim_id: 'claim_01',
      claim_text: 'Revidierbarkeit ist Bedingung für Akzeptanz.',
      confidence_label: 'medium',
      confidence_score: 0.5,
      evidence: [{ evidence_id: 'ev_1' }],
    } as ReportSection['claims'][number],
  ],
  hypotheses: [],
  hypotheses_appendix: [],
  data_gaps: [
    {
      gap_id: 'gap_01',
      claim_text: 'Keine Zeitmessung aus dem Schichtbetrieb.',
      gap_reason: 'Vorher-Messung fehlt',
    } as ReportSection['data_gaps'][number],
  ],
  structured_metadata: {},
  generation_failed: false,
  unbound_evidence_refs: [],
  unverified_statements: [],
}

function mountRail(
  redTeamFindings: string[] = [],
  overrides: Partial<ReportSection> = {},
  index: EvidenceIndex = evidenceIndex,
) {
  return mount(ReportEvidenceRail, {
    props: {
      section: { ...section, ...overrides },
      sectionNum: 3,
      evidenceIndex: index,
      redTeamFindings,
    },
    global: { plugins: [i18n] },
  })
}

describe('ReportEvidenceRail', () => {
  it('zeigt Claims mit Confidence-Wort statt nur Prozentzahl', () => {
    const wrapper = mountRail()
    const claim = wrapper.find(`[data-testid="${ReportReaderTestId.claim}"]`)
    expect(claim.exists()).toBe(true)
    expect(claim.text()).toContain('mittel')
    expect(claim.text()).toContain('claim_01')
  })

  it('rendert gebundene Belege mit Anker-Link', async () => {
    const wrapper = mountRail()
    expect(wrapper.text()).toContain('Pflegeteam Station 3')
    const anchorBtn = wrapper.find('.evrow-anchor')
    expect(anchorBtn.exists()).toBe(true)
    await anchorBtn.trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['agent-log:entry-42']])
  })

  it('rendert Datenluecken des Abschnitts', () => {
    const wrapper = mountRail()
    const gap = wrapper.find(`[data-testid="${ReportReaderTestId.gap}"]`)
    expect(gap.exists()).toBe(true)
    expect(gap.text()).toContain('Keine Zeitmessung')
  })

  it('zeigt einen Red-Team-Block, wenn Befunde vorliegen', () => {
    const wrapper = mountRail(['Spannung zwischen Abschnitt 3 und 6.'])
    const redTeam = wrapper.find(`[data-testid="${ReportReaderTestId.redTeam}"]`)
    expect(redTeam.exists()).toBe(true)
    expect(redTeam.text()).toContain('Spannung zwischen Abschnitt 3 und 6.')
  })

  it('zeigt keinen Red-Team-Block ohne Befunde', () => {
    const wrapper = mountRail([])
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.redTeam}"]`).exists()).toBe(false)
  })

  // ---- Regressionen aus dem PR-6-Review (Codex) ----

  it('Regression: Evidence ohne quote zeigt den Pflicht-snippet statt nur den Quellennamen', () => {
    // `quote` ist optional, `snippet` Pflichtfeld (EvidenceRecordModel,
    // min_length=1). Der Belegrand zeigte ohne Zitat nur die Quelle — der Beleg
    // stand damit ohne jeden Inhalt da.
    const ohneZitat: EvidenceIndex = {
      ev_1: { ...evidenceIndex.ev_1, quote: undefined } as EvidenceIndex[string],
    }
    const wrapper = mountRail([], {}, ohneZitat)
    const rail = wrapper.find(`[data-testid="${ReportReaderTestId.rail}"]`)
    expect(rail.text()).toContain('Zeitersparnis ist eine Zahl aus der Präsentation.')
    expect(wrapper.find('.evrow-snippet').exists()).toBe(true)
  })

  it('Regression: Hypothesen aus dem Anhang zaehlen und erscheinen mit', async () => {
    // `hypotheses` ist auf fuenf gedeckelt, der Ueberhang steht in
    // `hypotheses_appendix`. Wer nur die erste Liste liest, blendet ihn aus.
    const mkHypo = (id: string, text: string) =>
      ({
        hypothesis_id: id,
        hypothesis_text: text,
        rationale: 'Begruendung',
        suggested_evidence: [],
      }) as unknown as ReportSection['hypotheses'][number]

    const wrapper = mountRail([], {
      hypotheses: [mkHypo('h_1', 'Gedeckelte Hypothese')],
      hypotheses_appendix: [mkHypo('h_2', 'Hypothese aus dem Anhang')],
    })

    const tab = wrapper.find('[data-testid="hypotheses-tab"]')
    expect(tab.text()).toContain('2')
    await tab.trigger('click')
    const rail = wrapper.find(`[data-testid="${ReportReaderTestId.rail}"]`)
    expect(rail.text()).toContain('Gedeckelte Hypothese')
    expect(rail.text()).toContain('Hypothese aus dem Anhang')
  })
})

