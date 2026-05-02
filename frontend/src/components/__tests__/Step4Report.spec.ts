/**
 * Step4Report — strict-Zod-Parse Tests (Sub-Slice 15, Issue #172).
 *
 * Prueft:
 * - Gueltiger Payload: kein schemaError, normales Rendering.
 * - Unbekanntes Top-Level-Feld in Report (strict): schemaError gesetzt, Banner sichtbar.
 * - Fehlendes confidence_label im Claim: EvidenceMap-Parse schlaegt fehl → schemaError.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'

// localStorage muss vor allen Modul-Imports gemockt sein,
// da i18n/index.js bei Import-Zeit localStorage.getItem aufruft.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// Mock die gesamte API-Schicht
vi.mock('../../api/report', () => ({
  generateReport: vi.fn(),
  getAgentLog: vi.fn().mockResolvedValue(null),
  getConsoleLog: vi.fn().mockResolvedValue(null),
  getReport: vi.fn(),
  getReportStatus: vi.fn(),
  getReportEvidence: vi.fn(),
  exportReport: vi.fn(),
}))
vi.mock('../../api/simulation', () => ({
  createSimulationBranch: vi.fn(),
  getAvailableModels: vi.fn().mockResolvedValue({ success: true, data: { ollama: [], presets: [], current_default: '' } }),
}))

import { getReport, getReportStatus, getReportEvidence } from '../../api/report'
import Step4Report from '../Step4Report.vue'

// Minimaler i18n-Stub
const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      'step4.title': 'Bericht',
      'step4.sub': 'Simulationsbericht',
      'step4.view.sections': 'Abschnitte',
      'step4.view.tools': 'Tools',
      'step4.next': 'Weiter',
      'step4.quote.openSource': 'Quelle öffnen',
      'common.completed': 'Fertig',
      'common.running': 'Laufend',
      'common.ready': 'Bereit',
      'errors.reportFailed': 'Fehler',
    },
  },
})

// Minimaler Router-Stub
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div/>' } },
    { path: '/interaction/:reportId', name: 'Interaction', component: { template: '<div/>' } },
    { path: '/simulation/:simulationId', name: 'Simulation', component: { template: '<div/>' } },
  ],
})

// Stubs fuer interne UI-Komponenten
const globalStubs = {
  Btn: { template: '<button><slot /></button>' },
  Badge: { template: '<span><slot /></span>' },
  Kicker: { template: '<span><slot /></span>' },
  Select: { template: '<select />' },
}

// Valides Report-Payload (ReportSchema-konform)
const VALID_REPORT = {
  schema_version: 2,
  report_id: 'report_test01',
  simulation_id: 'sim_test01',
  graph_id: 'graph_test01',
  simulation_requirement: 'Test-Anforderung fuer Vitest',
  status: 'completed',
  markdown_content: '# Testbericht\n\nInhalt.',
  has_evidence: false,
  evidence_sections: 0,
}

// Valides EvidenceMap-Payload
const VALID_EVIDENCE: object = {
  schema_version: 2,
  report_id: 'report_test01',
  simulation_id: 'sim_test01',
  global_evidence: [],
  sections: [],
}

// Hilfsfunktion zum Mounten
function mountComponent(props = {}) {
  return mount(Step4Report, {
    props: { reportId: 'report_test01', ...props },
    global: {
      plugins: [router, i18n],
      stubs: globalStubs,
    },
  })
}

describe('Step4Report — strict-Zod-Parse (Sub-Slice 15)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Standard-Status: completed + vollstaendiger Payload
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_REPORT,
    })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_EVIDENCE,
    })
  })

  it('zeigt keinen schema-error-Banner bei validem Payload', async () => {
    const wrapper = mountComponent()
    // Warten bis alle Promises resolved sind
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.schema-error').exists()).toBe(false)
  })

  it('zeigt schema-error-Banner wenn Report ein unbekanntes Top-Level-Feld hat (.strict())', async () => {
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { ...VALID_REPORT, unknown_extra_field: 'dieser wert sollte Zod strict brechen' },
    })

    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.schema-error').exists()).toBe(true)
    expect(wrapper.find('.schema-error').text()).toContain('report')
  })

  it('zeigt schema-error-Banner wenn EvidenceMap fehlendes Pflichtfeld hat', async () => {
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        schema_version: 2,
        report_id: 'report_test01',
        // simulation_id fehlt — Pflichtfeld
        global_evidence: [],
        sections: [],
      },
    })

    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.schema-error').exists()).toBe(true)
    expect(wrapper.find('.schema-error').text()).toContain('evidence')
  })
})

// Sub-Slice 16b: klickbare Quotes + source_id_anchor-Scroll (Refs #173)
import { parseSourceAnchor, entryAnchorId } from '../../utils/sourceAnchor'

describe('Quote + Anchor (Sub-Slice 16b)', () => {
  // EvidenceMap mit einem Item, das quote + source_id_anchor hat
  const EVIDENCE_WITH_QUOTE = {
    schema_version: 2,
    report_id: 'report_test01',
    simulation_id: 'sim_test01',
    global_evidence: [],
    sections: [
      {
        section_index: 1,
        section_title: 'Abschnitt mit Quote',
        section_summary: 'Zusammenfassung mit Quote-Evidence',
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Claim-Text mit ausreichend Zeichen fuer Zod',
            confidence_label: 'high',
            confidence_score: 0.85,
            evidence: [
              {
                type: 'graph_fact',
                source: 'neo4j',
                snippet: 'Snippet-Text ohne Quote',
                supports_claim: true,
                match_score: 0.9,
                quote: 'Dies ist ein wörtliches Zitat aus der Quelle.',
                source_id_anchor: 'agent-log-1#entry-testentry',
              },
            ],
            audit_trail: [],
          },
        ],
      },
    ],
  }

  const EVIDENCE_WITHOUT_QUOTE = {
    schema_version: 2,
    report_id: 'report_test01',
    simulation_id: 'sim_test01',
    global_evidence: [],
    sections: [
      {
        section_index: 1,
        section_title: 'Abschnitt ohne Quote',
        section_summary: 'Zusammenfassung ohne Quote',
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Claim-Text mit ausreichend Zeichen fuer Zod',
            confidence_label: 'high',
            confidence_score: 0.85,
            evidence: [
              {
                type: 'graph_fact',
                source: 'neo4j',
                snippet: 'Nur Snippet, kein Quote',
                supports_claim: true,
                match_score: 0.9,
              },
            ],
            audit_trail: [],
          },
        ],
      },
    ],
  }

  function mountWithEvidence(evidenceData: object) {
    vi.clearAllMocks()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_REPORT,
    })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: evidenceData,
    })
    return mountComponent()
  }

  async function waitForRender(wrapper: ReturnType<typeof mountComponent>) {
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 80))
    await wrapper.vm.$nextTick()
  }

  it('rendert blockquote wenn item.quote gesetzt ist', async () => {
    const wrapper = mountWithEvidence(EVIDENCE_WITH_QUOTE)
    await waitForRender(wrapper)

    // Evidence-Panel wird nur angezeigt wenn Sections vorhanden
    // Erste Section muss ausgewählt sein (automatisch durch loadEvidence)
    const blockquote = wrapper.find('blockquote.evidence-quote')
    expect(blockquote.exists()).toBe(true)
    expect(blockquote.text()).toContain('wörtliches Zitat')
  })

  it('rendert span statt blockquote wenn item.quote null ist', async () => {
    const wrapper = mountWithEvidence(EVIDENCE_WITHOUT_QUOTE)
    await waitForRender(wrapper)

    expect(wrapper.find('blockquote.evidence-quote').exists()).toBe(false)
  })

  it('rendert anchor-button wenn item.source_id_anchor gesetzt ist', async () => {
    const wrapper = mountWithEvidence(EVIDENCE_WITH_QUOTE)
    await waitForRender(wrapper)

    const btn = wrapper.find('button.evidence-anchor-link')
    expect(btn.exists()).toBe(true)
  })

  it('click auf web-anchor ruft window.open auf', async () => {
    const EVIDENCE_WEB = {
      ...EVIDENCE_WITH_QUOTE,
      sections: [
        {
          ...EVIDENCE_WITH_QUOTE.sections[0],
          claims: [
            {
              ...EVIDENCE_WITH_QUOTE.sections[0].claims[0],
              evidence: [
                {
                  ...EVIDENCE_WITH_QUOTE.sections[0].claims[0].evidence[0],
                  source_id_anchor: 'web:https://example.com/artikel',
                },
              ],
            },
          ],
        },
      ],
    }

    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mountWithEvidence(EVIDENCE_WEB)
    await waitForRender(wrapper)

    const btn = wrapper.find('button.evidence-anchor-link')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(openSpy).toHaveBeenCalledWith('https://example.com/artikel', '_blank', 'noopener,noreferrer')
    openSpy.mockRestore()
  })
})

// Sub-Slice 16a: aggregateSectionConfidence + ConfidenceBadge in Step4Report (Refs #173)
import { aggregateSectionConfidence } from '../../utils/confidenceUtils'

describe('aggregateSectionConfidence (Sub-Slice 16a)', () => {
  it('gibt score=0 und label=low zurück für leere claims-Liste', () => {
    const result = aggregateSectionConfidence({ claims: [] })
    expect(result.score).toBe(0)
    expect(result.label).toBe('low')
    expect(result.auditTrail).toEqual([])
  })

  it('berechnet arithmetisches Mittel der confidence_scores', () => {
    const section = {
      claims: [
        { confidence_score: 0.8, confidence_label: 'high', audit_trail: [] },
        { confidence_score: 0.6, confidence_label: 'medium', audit_trail: [] },
      ],
    }
    const result = aggregateSectionConfidence(section)
    // (0.8 + 0.6) / 2 = 0.7000
    expect(result.score).toBe(0.7)
    expect(result.label).toBe('medium')
  })

  it('rundet auf 4 Dezimalstellen', () => {
    const section = {
      claims: [
        { confidence_score: 1 / 3, confidence_label: 'low', audit_trail: [] },
      ],
    }
    const result = aggregateSectionConfidence(section)
    // 0.33333... → 0.3333
    expect(result.score).toBe(0.3333)
  })

  it('ist deterministisch — gleicher Input ergibt gleichen Output', () => {
    const section = {
      claims: [
        { confidence_score: 0.9, confidence_label: 'verified', audit_trail: [{ type: 'graph_fact', source: 's1' }] },
        { confidence_score: 0.5, confidence_label: 'medium', audit_trail: [{ type: 'agent_action', source: 's2' }] },
      ],
    }
    const r1 = aggregateSectionConfidence(section)
    const r2 = aggregateSectionConfidence(section)
    expect(r1.score).toBe(r2.score)
    expect(r1.label).toBe(r2.label)
    expect(r1.auditTrail.length).toBe(r2.auditTrail.length)
  })

  it('flacht audit_trail über alle Claims flach', () => {
    const section = {
      claims: [
        { confidence_score: 0.8, confidence_label: 'high', audit_trail: [{ source: 'a' }, { source: 'b' }] },
        { confidence_score: 0.6, confidence_label: 'medium', audit_trail: [{ source: 'c' }] },
      ],
    }
    const result = aggregateSectionConfidence(section)
    expect(result.auditTrail).toHaveLength(3)
  })
})

describe('Step4Report — ConfidenceBadge-Integration (Sub-Slice 16a)', () => {
  const VALID_EVIDENCE_WITH_SECTIONS = {
    schema_version: 2,
    report_id: 'report_test01',
    simulation_id: 'sim_test01',
    global_evidence: [],
    sections: [
      {
        section_index: 1,
        section_title: 'Abschnitt 1',
        section_summary: 'Zusammenfassung 1',
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Erster Claim mit genug Länge für Zod-Validierung',
            confidence_label: 'high',
            confidence_score: 0.8,
            evidence: [
              {
                type: 'graph_fact',
                source: 'neo4j',
                snippet: 'Graph-Fakt A',
                supports_claim: true,
                match_score: 0.9,
              },
            ],
            audit_trail: [{ source: 'graph_tool', snippet: 'Audit A' }],
          },
        ],
      },
      {
        section_index: 2,
        section_title: 'Abschnitt 2',
        section_summary: 'Zusammenfassung 2',
        claims: [
          {
            claim_id: 'claim_02',
            claim_text: 'Zweiter Claim mit ausreichend Text für Validierung',
            confidence_label: 'medium',
            confidence_score: 0.5,
            evidence: [],
            audit_trail: [{ source: 'agent_log', snippet: 'Audit B' }],
          },
        ],
      },
    ],
  }

  const VALID_OUTLINE_2SECTIONS = {
    title: 'Test-Report',
    summary: 'Zusammenfassung',
    sections: [
      { title: 'Abschnitt 1', description: 'Beschreibung 1' },
      { title: 'Abschnitt 2', description: 'Beschreibung 2' },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        status: 'completed',
        report_id: 'report_test01',
        simulation_id: 'sim_test01',
        outline: VALID_OUTLINE_2SECTIONS,
      },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_REPORT,
    })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_EVIDENCE_WITH_SECTIONS,
    })
  })

  it('rendert 2 ConfidenceBadge-Instanzen für 2 Sections mit Evidence', async () => {
    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 80))
    await wrapper.vm.$nextTick()

    const badges = wrapper.findAllComponents({ name: 'ConfidenceBadge' })
    expect(badges.length).toBeGreaterThanOrEqual(2)
  })
})
