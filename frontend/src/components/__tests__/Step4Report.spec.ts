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
import type { Report, EvidenceMap } from '../../contracts/reportContract'

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
  generateReport: vi.fn().mockResolvedValue({ success: true, data: { report_id: 'report_test01' } }),
  getAgentLog: vi.fn().mockResolvedValue(null),
  getConsoleLog: vi.fn().mockResolvedValue(null),
  getReport: vi.fn(),
  getReportStatus: vi.fn(),
  getReportEvidence: vi.fn(),
  exportReport: vi.fn(),
}))
vi.mock('../../api/simulation', () => ({
  createSimulationBranch: vi.fn(),
}))
// Slice A1: ReportModelControls importiert ModelPicker, der auf useLlmProvidersStore
// zugreift. Stub die ganze Komponente weg, damit die Step4Report-Tests ohne Pinia-
// Setup mounten und sich auf den Report-Workflow konzentrieren können. Die Picker-
// Logik wird separat in ModelPicker.spec.ts abgedeckt.
vi.mock('../step4/ReportModelControls.vue', () => ({
  default: {
    name: 'ReportModelControls',
    template: '<div data-testid="report-model-controls" />',
    props: ['modelValue', 'isRegenerating'],
    emits: ['update:modelValue', 'regenerate'],
  },
}))

// Mock useIncrementalLogPolling — Sub-Slice J.3 (#221): erlaubt Intervall-Prüfung ohne echten Polling-Timer
vi.mock('../../composables/useIncrementalLogPolling', async () => {
  const { ref } = await import('vue')
  return {
    useIncrementalLogPolling: vi.fn(() => ({
      lines: ref([]),
      polling: { start: vi.fn(), stop: vi.fn() },
      reset: vi.fn(),
    })),
  }
})

// Phase-1 Kanon-First: Step4Report initialisiert reportRoute in onMounted aus
// dem Kanon (routing/defaults.global_default via useEffectiveModelSelection.
// effectiveRef); Picker-Picks sind transient (KEIN setGlobalSelection, nicht
// persistiert). STORAGE_REPORT_AI_REF (agora.report.aiModelRef) ist entfernt,
// STORAGE_REPORT_ROUTE_LEGACY (agora.report.route) wird nur noch defensiv
// gelöscht. ReportModelControls bleibt gestubbt. Der Mock ersetzt das Composable
// (das Pinia-Stores instanziiert) mit steuerbaren Refs, damit die Specs ohne
// Pinia-Setup mounten.
import { ref as mockRef, type Ref as MockRef } from 'vue'
import type { AiModelRef } from '../../contracts/aiModelRef'

// Steuerbarer Kanon-Stub. Defaults: leerer Kanon (effectiveRef=null), wie er
// von useEffectiveModelSelection vor ensureLoaded/Routing-Load geliefert wird.
const mockEffectiveRef: MockRef<AiModelRef | null> = mockRef<AiModelRef | null>(null)
const mockEffectiveRoute: MockRef<unknown> = mockRef<unknown>(null)
const mockLoading: MockRef<boolean> = mockRef<boolean>(false)
const mockError: MockRef<string | null> = mockRef<string | null>(null)
const mockEnsureLoaded = vi.fn().mockResolvedValue(undefined)
const mockSetGlobalSelection = vi.fn().mockResolvedValue(undefined)

function resetMockSelection(): void {
  mockEffectiveRef.value = null
  mockEffectiveRoute.value = null
  mockLoading.value = false
  mockError.value = null
  mockEnsureLoaded.mockResolvedValue(undefined)
  mockSetGlobalSelection.mockReset()
  mockSetGlobalSelection.mockResolvedValue(undefined)
}

vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: mockEffectiveRef,
    effectiveRoute: mockEffectiveRoute,
    loading: mockLoading,
    error: mockError,
    ensureLoaded: mockEnsureLoaded,
    setGlobalSelection: mockSetGlobalSelection,
  }),
}))

import { generateReport, getReport, getReportStatus, getReportEvidence } from '../../api/report'
import { useIncrementalLogPolling } from '../../composables/useIncrementalLogPolling'
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
      'reportMode.label': 'Report-Modus',
      'reportMode.strict.label': 'Strikt',
      'reportMode.strict.hint': 'Nur belegte Claims.',
      'reportMode.balanced.label': 'Ausgewogen (Standard)',
      'reportMode.balanced.hint': 'Belegte Claims plus markierte Hypothesen.',
      'reportMode.explorative.label': 'Explorativ',
      'reportMode.explorative.hint': 'Alle Claims, EXPLORATIVE-Banner.',
      'step4.reportConfirm.title': 'Report starten?',
      'step4.reportConfirm.description': 'Simulation abgeschlossen. Modell wählen und starten.',
      'step4.reportConfirm.startButton': 'Report starten',
      'step4.reportConfirm.stopButton': 'Abbrechen',
      'step4.reportConfirm.stopDisabledTip': 'Abbruch verfügbar nach Backend-Slice 6',
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
  LlmProfilePicker: true,
  ReportBranchControls: true,
}

// Valides Report-Payload (ReportSchema-konform)
const VALID_REPORT: Report = {
  schema_version: 2,
  report_id: 'report_test01',
  simulation_id: 'sim_test01',
  graph_id: 'graph_test01',
  simulation_requirement: 'Test-Anforderung fuer Vitest',
  status: 'completed',
  markdown_content: '# Testbericht\n\nInhalt.',
  missing_sections: [],
  has_evidence: false,
  red_team_findings: [],
  evidence_sections: 0,
}

// Valides EvidenceMap-Payload
const VALID_EVIDENCE: EvidenceMap = {
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
    resetMockSelection()
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
        hypotheses: [
          {
            hypothesis_id: 'hypothesis_01',
            hypothesis_text: 'Indizien legen eine zweite Zielgruppe nahe.',
            rationale: 'Es fehlt noch direkte Evidence aus einer zweiten Stakeholder-Gruppe.',
            suggested_evidence: ['Persona-Interview aus Gruppe B ergänzen'],
          },
        ],
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Claim-Text mit ausreichend Zeichen fuer Zod',
            // ADR-0002 Anker 4 (Sub-Slice M11.7b): high braeuchte 2 Stakeholder-
            // Gruppen — fuer den Quote/Anchor-Test nicht relevant, daher medium.
            confidence_label: 'medium',
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
            // ADR-0002 Anker 4 (Sub-Slice M11.7b): siehe oben.
            confidence_label: 'medium',
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
    resetMockSelection()
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

  it('rendert hypotheses separat von Claims', async () => {
    const wrapper = mountWithEvidence(EVIDENCE_WITH_QUOTE)
    await waitForRender(wrapper)

    const hypothesisTab = wrapper.find('[data-testid="hypotheses-tab"]')
    expect(hypothesisTab.exists()).toBe(true)
    await hypothesisTab.trigger('click')
    await wrapper.vm.$nextTick()

    const hypothesis = wrapper.find('.hypothesis-card')
    expect(hypothesis.exists()).toBe(true)
    expect(hypothesis.text()).toContain('hypothesis_01')
    expect(hypothesis.text()).toContain('zweite Zielgruppe')
    expect(hypothesis.text()).toContain('Persona-Interview')
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
  it('gibt score=0 und label=speculative zurück für leere claims-Liste', () => {
    const result = aggregateSectionConfidence({ claims: [] })
    expect(result.score).toBe(0)
    expect(result.label).toBe('speculative')
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

// Sub-Slice J.3 (#221): agentLog-Polling-Intervall auf 2500 ms angeglichen
describe('Step4Report — agentLog-Polling-Intervall (Sub-Slice J.3)', () => {
  beforeEach(() => {
    resetMockSelection()
  })

  it('ruft useIncrementalLogPolling für agentLog mit intervalMs=2500 auf', async () => {
    vi.mocked(getReportStatus).mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: VALID_REPORT,
    })
    vi.mocked(getReportEvidence).mockResolvedValue({
      success: true,
      data: VALID_EVIDENCE,
    })

    const mockPolling = vi.mocked(useIncrementalLogPolling)

    mountComponent()

    // agentLog-Aufruf ist der erste Aufruf (mit parseLine: parseAgentEntry).
    // consoleLog-Aufruf hat kein parseLine und bleibt bei 2000 ms.
    const agentCall = mockPolling.mock.calls.find(
      (args) => typeof args[0].parseLine === 'function'
    )
    expect(agentCall).toBeDefined()
    expect(agentCall![0]).toMatchObject({ intervalMs: 2500 })
  })

  it('consoleLog-Polling bleibt bei 2000 ms (unverändert)', () => {
    const mockPolling = vi.mocked(useIncrementalLogPolling)

    mountComponent()

    const consoleCall = mockPolling.mock.calls.find(
      (args) => typeof args[0].parseLine !== 'function'
    )
    expect(consoleCall).toBeDefined()
    expect(consoleCall![0]).toMatchObject({ intervalMs: 2000 })
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
            // ADR-0002 Anker 4 (Sub-Slice M11.7b): high braeuchte 2 Stakeholder-
            // Gruppen — fuer den ConfidenceBadge-Render-Test ist medium aequivalent.
            confidence_label: 'medium',
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
            evidence: [
              {
                type: 'graph_fact',
                source: 'neo4j',
                snippet: 'Graph-Fakt B',
                supports_claim: true,
                match_score: 0.6,
              },
            ],
            audit_trail: [{ source: 'agent_log', snippet: 'Audit B' }],
          },
        ],
      },
      {
        section_index: 3,
        section_title: 'Abschnitt 3',
        section_summary: 'Zusammenfassung 3 — spekulativer Bereich',
        // speculative-Claim: kein Evidence nötig (laut ADR-0002 Anker)
        claims: [
          {
            claim_id: 'claim_03',
            claim_text: 'Spekulativer Claim ohne belastbare Evidence — Frühindikator',
            confidence_label: 'speculative',
            confidence_score: 0.1,
            evidence: [],
            audit_trail: [],
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
      { title: 'Abschnitt 3', description: 'Beschreibung 3 — spekulativ' },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    resetMockSelection()
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

// P4.1 Frontend-Teil: localStorage-Round-Trip + generateReport-Mode-Übergabe
describe('Step4Report — Report-Modus-Persistenz und API-Übergabe (P4.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    resetMockSelection()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
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

  it('liest reportMode aus localStorage und schreibt bei Änderung zurück', async () => {
    localStorageMock.setItem('agora.reportMode', 'strict')

    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await wrapper.vm.$nextTick()

    // Wert aus localStorage muss initial "strict" sein
    const vm = wrapper.vm as unknown as { reportMode: string }
    expect(vm.reportMode).toBe('strict')

    // Änderung schreibt zurück
    ;(vm as unknown as { reportMode: string }).reportMode = 'explorative'
    await wrapper.vm.$nextTick()
    expect(localStorageMock.getItem('agora.reportMode')).toBe('explorative')
  })

  it('fällt auf "balanced" zurück wenn localStorage-Wert ungültig', async () => {
    localStorageMock.setItem('agora.reportMode', 'invalid_mode')

    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await wrapper.vm.$nextTick()

    const vm = wrapper.vm as unknown as { reportMode: string }
    expect(vm.reportMode).toBe('balanced')
  })

  it('übergibt reportMode als mode-Parameter an generateReport', async () => {
    localStorageMock.setItem('agora.reportMode', 'strict')

    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await wrapper.vm.$nextTick()

    // regenerateWithModel direkt aufrufen
    await (wrapper.vm as unknown as { regenerateWithModel: () => Promise<void> }).regenerateWithModel()
    await wrapper.vm.$nextTick()

    expect(generateReport).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'strict' })
    )
  })
})

// Sub-Slice Confirm-Dialog + Stop-Button (2026-05-16)
describe('Step4Report — Confirm-Dialog + Stop-Button', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    resetMockSelection()
  })

  it('zeigt Confirm-Dialog wenn kein reportId und Status idle (reportPending=true)', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })

    // Kein reportId → onMounted setzt reportPending=true
    const wrapper = mount(Step4Report, {
      props: { simulationId: 'sim_test01' },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="report-confirm-block"]').exists()).toBe(true)
  })

  it('Confirm-Dialog nicht sichtbar wenn reportId gesetzt (Report läuft bereits)', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })

    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="report-confirm-block"]').exists()).toBe(false)
  })

  it('Klick auf "Report starten" ruft generateReport auf', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })
    ;(generateReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { report_id: 'report_new01' },
    })

    const wrapper = mount(Step4Report, {
      props: { simulationId: 'sim_test01' },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    const btn = wrapper.find('[data-testid="report-confirm-start-btn"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await wrapper.vm.$nextTick()

    expect(generateReport).toHaveBeenCalledWith(
      expect.objectContaining({ simulation_id: 'sim_test01' })
    )
  })

  it('Stop-Button ist disabled wenn cancelEndpointAvailable=false', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })

    const wrapper = mount(Step4Report, {
      props: { simulationId: 'sim_test01', cancelEndpointAvailable: false },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    // Disabled-Button hat das disabled-Attribut
    const stopBtn = wrapper.find('.stop-btn[disabled]')
    expect(stopBtn.exists()).toBe(true)
  })

  it('Stop-Button emittet "stop" wenn cancelEndpointAvailable=true', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })

    const wrapper = mount(Step4Report, {
      props: { simulationId: 'sim_test01', cancelEndpointAvailable: true },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 50))
    await wrapper.vm.$nextTick()

    const stopBtn = wrapper.find('.stop-btn--active')
    expect(stopBtn.exists()).toBe(true)
    await stopBtn.trigger('click')

    expect(wrapper.emitted('stop')).toBeTruthy()
    expect(wrapper.emitted('stop')!.length).toBe(1)
  })
})

// Slice A1 (2026-05-17): Provider-Override + DB-Key-Fallback-Tests (Copilot
// PR #466) wurden mit der Migration auf den projektweiten ModelPicker
// entfernt. Provider-Credentials laufen jetzt zentral über
// `/settings/llm-providers` → `LlmProviderSecretsStore` → SecretResolver.
// Step4Report sendet nur noch `llm_model`; der Provider wird serverseitig
// aufgelöst. Siehe PR-Beschreibung Slice A1.

// Phase-1 Kanon-First (frontend-next): reportRoute wird in onMounted aus dem
// Kanon (useEffectiveModelSelection.effectiveRef) initialisiert. Picker-Picks
// sind transient und persistieren NICHT (kein setGlobalSelection-Aufruf, keine
// agora.report.aiModelRef-Senke mehr). Legacy-STORAGE_REPORT_ROUTE_LEGACY wird
// nur defensiv gelöscht.
describe('Step4Report — Kanon-First Initialisierung (Phase 1)', () => {
  const KANON_REF: AiModelRef = {
    provider_connection_id: 'conn_kanon',
    model_id: 'kanon-model-1',
    source: 'workspace-default',
  } as AiModelRef

  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    resetMockSelection()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })
  })

  it('initialisiert reportRoute aus dem Kanon (effectiveRef) in onMounted', async () => {
    mockEffectiveRef.value = KANON_REF

    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(mockEnsureLoaded).toHaveBeenCalled()
    const vm = wrapper.vm as unknown as { reportRoute: AiModelRef | null }
    expect(vm.reportRoute).toEqual(KANON_REF)
  })

  it('lässt reportRoute null wenn der Kanon leer ist (effectiveRef=null)', async () => {
    // mockEffectiveRef bleibt null nach resetMockSelection
    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()
    await wrapper.vm.$nextTick()

    const vm = wrapper.vm as unknown as { reportRoute: AiModelRef | null }
    expect(vm.reportRoute).toBeNull()
  })

  it('ruft setGlobalSelection NICHT beim Picker-Pick auf (Picker ist transient)', async () => {
    mockEffectiveRef.value = KANON_REF

    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()
    await wrapper.vm.$nextTick()

    // Simuliere einen transienten Picker-Pick via ReportModelControls-Stub-emit.
    const controls = wrapper.findComponent({ name: 'ReportModelControls' })
    expect(controls.exists()).toBe(true)
    await controls.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn_other',
      model_id: 'picked-model',
      source: 'explicit',
    } as AiModelRef)
    await wrapper.vm.$nextTick()

    // Picker-Pick ändert reportRoute transient, persistiert aber NICHT den Kanon.
    expect(mockSetGlobalSelection).not.toHaveBeenCalled()
  })

  it('löscht STORAGE_REPORT_ROUTE_LEGACY (agora.report.route) defensiv in onMounted', async () => {
    localStorageMock.setItem('agora.report.route', 'some-legacy-route')

    mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()

    expect(localStorageMock.getItem('agora.report.route')).toBeNull()
  })
})

// Issue #817: der Report-Start überträgt die vollständige kanonische Auswahl
// (ai_model_ref) und kombiniert sie nicht mit dem Legacy-Profil.
describe('Step4Report — Report-Route-SSoT-Payload (#817)', () => {
  const PICK: AiModelRef = {
    provider_connection_id: 'conn_minimax',
    model_id: 'MiniMax-M3',
    source: 'explicit',
  } as AiModelRef

  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    resetMockSelection()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'idle' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_EVIDENCE })
    ;(generateReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { report_id: 'report_new01' },
    })
  })

  async function callRegenerate(): Promise<Record<string, unknown>> {
    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()
    await wrapper.vm.$nextTick()
    await (wrapper.vm as unknown as { regenerateWithModel: () => Promise<void> }).regenerateWithModel()
    await wrapper.vm.$nextTick()
    return vi.mocked(generateReport).mock.calls.at(-1)![0] as Record<string, unknown>
  }

  it('sendet ai_model_ref und kein konkurrierendes llm_profile_id bei explizitem Pick', async () => {
    mockEffectiveRef.value = PICK
    // Veraltetes Legacy-Profil im localStorage darf den Pick NICHT begleiten.
    localStorageMock.setItem('agora.report.llmProfileId', 'prof-stale')

    const payload = await callRegenerate()

    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn_minimax',
      model_id: 'MiniMax-M3',
      source: 'explicit',
    })
    expect(payload.llm_profile_id).toBeUndefined()
    expect(payload.llm_model).toBeUndefined()
  })

  it('sendet ohne expliziten Pick keinen erfundenen Override', async () => {
    // effectiveRef bleibt null, kein Profil im Storage.
    const payload = await callRegenerate()

    expect(payload.ai_model_ref).toBeUndefined()
    expect(payload.llm_profile_id).toBeUndefined()
    expect(payload.llm_model).toBeUndefined()
    expect(payload.simulation_id).toBe('sim_test01')
  })

  it('fällt ohne Pick auf das Legacy-llm_profile_id zurück', async () => {
    localStorageMock.setItem('agora.report.llmProfileId', 'prof-legacy')

    const payload = await callRegenerate()

    expect(payload.llm_profile_id).toBe('prof-legacy')
    expect(payload.ai_model_ref).toBeUndefined()
  })
})
