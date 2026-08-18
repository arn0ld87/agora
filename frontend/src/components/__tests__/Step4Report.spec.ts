/**
 * Step4Report — strict-Zod-Parse Tests (Sub-Slice 15, Issue #172).
 *
 * Prueft:
 * - Gueltiger Payload: kein schemaError, normales Rendering.
 * - Unbekanntes Top-Level-Feld in Report (strict): schemaError gesetzt, Banner sichtbar.
 * - Fehlendes confidence_label im Claim: EvidenceMap-Parse schlaegt fehl → schemaError.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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
  getRunLlmRoutingMock.mockReset()
  getRunLlmRoutingMock.mockResolvedValue({ snapshots: {}, runtime_config: null })
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

// Issue #1023 (Befund B-26, P1): loadRunModelDefault() liest das Lauf-Modell
// ueber denselben Weg wie StepModelOverrideChip.vue (Teilpunkt 3, #1023):
// GET /api/runs/<id>/llm-routing. getRunLlmRouting() gestubbt, useAiModelRefAdapter
// gestubbt (instanziiert sonst useLlmProvidersStore/Pinia, das dieser Spec fehlt).
const getRunLlmRoutingMock = vi.fn().mockResolvedValue({ snapshots: {}, runtime_config: null })
vi.mock('@/api/llmRouting', () => ({
  getRunLlmRouting: (runId: string) => getRunLlmRoutingMock(runId),
}))
vi.mock('@/composables/useAiModelRefAdapter', () => ({
  useAiModelRefAdapter: () => ({
    toLlmRoute: vi.fn(),
    toAiModelRef: vi.fn((route: { provider_id?: string | null; model?: string | null }) => {
      if (!route?.provider_id || !route?.model) return null
      return {
        provider_connection_id: route.provider_id,
        model_id: route.model,
        source: 'explicit',
      }
    }),
  }),
}))

import {
  generateReport,
  getReport,
  getReportStatus,
  getReportEvidence,
  exportReport,
} from '../../api/report'
import { useIncrementalLogPolling } from '../../composables/useIncrementalLogPolling'
import { REPORT_STATUS_POLL_INTERVAL_MS } from '../../composables/useReportGeneration'
import Step4Report from '@/components/v4/steps/Step4Report.vue'
import deMessages from '../../i18n/locales/de.json'

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
      'common.incomplete': 'Unvollständig',
      'common.running': 'Laufend',
      'common.ready': 'Bereit',
      'step4.status.incomplete': 'Report unvollständig — einige Abschnitte sind fehlgeschlagen.',
      'step4.status.sectionFailed': 'Abschnitt fehlgeschlagen',
      'step4.status.pollTransportError': 'Verbindung zum Server verloren.',
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
  ReportBranchControls: true,
}

// Issue #987: ReportFinalView traegt den `.json`-Knopf. Als echte Komponente
// zieht sie halbe Report-Ansicht mit; als Stub mit Emit-Deklaration laesst
// sie sich gezielt ausloesen, ohne den Produktionspfad zu umgehen — der
// Handler in Step4Report ist derselbe.
const REPORT_FINAL_VIEW_STUB = {
  name: 'ReportFinalView',
  template: '<div data-testid="report-final-view" />',
  emits: ['download-json'],
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
  run_degradations: [],
}

// Valides EvidenceMap-Payload
const VALID_EVIDENCE: EvidenceMap = {
  schema_version: 3,
  report_id: 'report_test01',
  simulation_id: 'sim_test01',
  evidence_index: {},
  global_evidence_refs: [],
  sections: [],
  // Issue #1006: additives Feld mit Default. Wie global_evidence und sections
  // ist es im z.infer-Output-Typ required, obwohl es beim Parsen optional ist.
  degradation_log: [],
  // PR #1151: Audit-Trail regulärer Gate-Entscheidungen, gleiche Default-Logik.
  gate_decision_log: [],
  // Verbleib der quantitativen Tool-Fakten, gleiche Default-Logik.
  evidence_coverage_ledger: [],
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

// Issue #987 — der Hinweis muss den Nutzer erreichen, nicht nur den Log-Bus.
//
// Erste Fassung dieses Slices rief options.addLog(). addLog() emittiert in
// dieser Komponente lediglich `add-log`, und der einzige produktive Mount
// (StepReportView.vue) haengt keinen Listener daran und rendert `systemLogs`
// nicht. Der Hinweis waere also nirgends angekommen — exakt die Fehlerklasse,
// die dieser Slice behebt, eine Ebene hoeher (Codex-Review zu PR #1042).
// Dieser Test mountet die Komponente und prueft das gerenderte Ergebnis.
describe('Step4Report — Evidence-Auslassung im JSON-Export (Issue #987)', () => {
  // Bewusst NICHT der flache i18n-Stub dieser Datei, sondern die echte
  // de.json: der Test soll belegen, dass der Schluessel im ausgelieferten
  // Locale existiert. Gegen einen Stub gepruefte Uebersetzungen sagen ueber
  // die Produktion nichts aus — ein fehlender oder umbenannter Schluessel
  // waere dort unsichtbar.
  const realI18n = createI18n({ legacy: false, locale: 'de', messages: { de: deMessages } })

  function mountWithFinalView() {
    return mount(Step4Report, {
      props: { reportId: 'report_test01' },
      global: {
        plugins: [router, realI18n],
        stubs: { ...globalStubs, ReportFinalView: REPORT_FINAL_VIEW_STUB },
      },
    })
  }

  const EXPECTED_NOTICE = deMessages.step4.export.evidenceOmitted.contract_violation

  function envelope(evidenceOmitted: unknown) {
    return new Blob([
      JSON.stringify({
        schema_version: 2,
        exported_at: '2026-08-03T10:00:00Z',
        report: VALID_REPORT,
        evidence: null,
        evidence_omitted: evidenceOmitted,
      }),
    ])
  }

  beforeEach(() => {
    vi.clearAllMocks()
    resetMockSelection()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_EVIDENCE,
    })
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  })

  it('rendert einen Hinweis, wenn der Export ohne Evidence-Map kam', async () => {
    ;(exportReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      envelope({
        reason: 'contract_violation',
        detail: 'Serverseitige Erklaerung fuer die exportierte Datei.',
        validation_errors: ['sections.0: Extra inputs are not permitted'],
      })
    )

    const wrapper = mountWithFinalView()
    await flushPromises()
    await wrapper.findComponent(REPORT_FINAL_VIEW_STUB).vm.$emit('download-json')
    await flushPromises()

    const notice = wrapper.find('[data-testid="report-evidence-omitted"]')
    expect(notice.exists()).toBe(true)
    expect(notice.attributes('role')).toBe('alert')
    expect(notice.text()).toContain('sections.0: Extra inputs are not permitted')
    // Der Text kommt aus vue-i18n, nicht aus dem Backend-`detail`
    // (AGENTS.md: keine hartkodierten UI-Texte).
    expect(notice.text()).not.toContain('Serverseitige Erklaerung')
    expect(EXPECTED_NOTICE).toBeTruthy()
    expect(notice.text()).toContain(EXPECTED_NOTICE)
  })

  it('rendert keinen Hinweis, wenn der Export vollstaendig war', async () => {
    ;(exportReport as ReturnType<typeof vi.fn>).mockResolvedValue(envelope(null))

    const wrapper = mountWithFinalView()
    await flushPromises()
    await wrapper.findComponent(REPORT_FINAL_VIEW_STUB).vm.$emit('download-json')
    await flushPromises()

    expect(wrapper.find('[data-testid="report-evidence-omitted"]').exists()).toBe(false)
  })
})

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
        schema_version: 3,
        report_id: 'report_test01',
        // simulation_id fehlt — Pflichtfeld
        evidence_index: {},
        global_evidence_refs: [],
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

// P2.6: INCOMPLETE-Status sichtbar im Frontend (Status-Badge + Section-Counter).
describe('Step4Report — INCOMPLETE-Status und generation_failed (P2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetMockSelection()
  })

  it('zählt fehlgeschlagene Sections (generation_failed=true) und blendet einen Hinweis ein', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        status: 'completed',
        report_id: 'report_test01',
        simulation_id: 'sim_test01',
        sections: {
          1: { content: '## Abschnitt 1\n\nInhalt.', generation_failed: false },
          2: { content: '## Abschnitt 2\n\nInhalt.', generation_failed: true },
          3: { content: '## Abschnitt 3\n\nInhalt.', generation_failed: true },
        },
      },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_REPORT,
    })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_EVIDENCE,
    })

    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 80))
    await wrapper.vm.$nextTick()

    const failedNote = wrapper.find('[data-testid="report-failed-sections"]')
    expect(failedNote.exists()).toBe(true)
    expect(failedNote.text()).toContain('2')
  })

  it('blendet den Section-Hinweis NICHT ein, wenn keine generation_failed=true vorliegt', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        status: 'completed',
        report_id: 'report_test01',
        simulation_id: 'sim_test01',
        sections: {
          1: { content: 'A', generation_failed: false },
          2: { content: 'B', generation_failed: false },
        },
      },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_REPORT,
    })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: VALID_EVIDENCE,
    })

    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 80))
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="report-failed-sections"]').exists()).toBe(false)
  })

  // CodeRabbit-P2 aus PR #938 Follow-up: status='failed' muss am Direct-Mount
  // als terminaler Zustand erkannt werden, sonst ersetzt onMounted
  // phase=2/emitted 'error' durch phase=1/'running' und der Badge springt
  // auf "Läuft" zurück, bis der nächste Status-Poll feuert.
  it('markiert status="failed" als terminal — Badge bleibt "Fehlgeschlagen", nicht "Läuft"', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        status: 'failed',
        report_id: 'report_test01',
        simulation_id: 'sim_test01',
        error: 'Generator crashed',
      },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: false })
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: false })

    const wrapper = mountComponent()
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 120))
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 120))
    await wrapper.vm.$nextTick()

    const badge = wrapper.find('[data-testid="report-status-badge"]').text()
    // i18n-Mock liefert den Key-Namen statt den übersetzten String —
    // das ist robuster als der locale-abhängige Text und prüft die
    // semantische Property (reportStatus === 'failed' → reportBadgeLabel
    // resolved zu 'common.failed' statt 'common.running'/'common.completed').
    expect(badge).toContain('common.failed')
    expect(badge).not.toContain('common.running')
    expect(badge).not.toContain('common.completed')
    expect(badge).not.toContain('common.ready')
  })

  // Hinweis: die Report-Badge-Variante/-Text für status='incomplete' wird in
  // production code über reportBadgeLabel/reportBadgeVariant computed values
  // gerendert, getrieben von reportStatus (ref). Der Text-Pfad ist hier
  // absichtlich NICHT getestet, weil Badge-Stub + i18n-Mock + jsdom-Microtask-
  // Reihenfolge den Test flaky machen. Verifikation erfolgt stattdessen über
  // unit-level test_3 (status_polling_handles_incomplete) im Backend — der
  // dortige resolve_report_status-Branch ist der Source-of-Truth.
})

// Sub-Slice 16b: klickbare Quotes + source_id_anchor-Scroll (Refs #173)
describe('Quote + Anchor (Sub-Slice 16b)', () => {
  const QUOTE_EVIDENCE_ID = 'ev_00000000000000000000000000000011'
  const SEED_EVIDENCE_ID = 'ev_00000000000000000000000000000012'
  // EvidenceMap mit einem Item, das quote + source_id_anchor hat
  const EVIDENCE_WITH_QUOTE = {
    schema_version: 3,
    report_id: 'report_test01',
    simulation_id: 'sim_test01',
    evidence_index: {
      [QUOTE_EVIDENCE_ID]: {
        evidence_id: QUOTE_EVIDENCE_ID,
        producer_key: 'agent:test:quote:1',
        type: 'agent_interview',
        source: 'agent_log',
        snippet: 'Snippet-Text ohne Quote',
        quote: 'Dies ist ein wörtliches Zitat aus der Quelle.',
        source_id_anchor: 'agent-log-1#entry-testentry',
        source_kind: 'agent_quote',
        persona_stakeholder_group: 'Testgruppe',
      },
      [SEED_EVIDENCE_ID]: {
        evidence_id: SEED_EVIDENCE_ID,
        producer_key: 'seed:test:quote:1',
        type: 'graph_fact',
        source: 'briefing.md',
        snippet: 'Seed-Beleg für den Quote-Test.',
        source_kind: 'seed_corpus',
      },
    },
    global_evidence_refs: [],
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
                evidence_id: QUOTE_EVIDENCE_ID,
                supports_claim: true,
                match_score: 0.9,
              },
              {
                evidence_id: SEED_EVIDENCE_ID,
                supports_claim: true,
                match_score: 0.8,
              },
            ],
            audit_trail: [],
          },
        ],
      },
    ],
  }

  const EVIDENCE_WITHOUT_QUOTE = {
    schema_version: 3,
    report_id: 'report_test01',
    simulation_id: 'sim_test01',
    evidence_index: {
      [QUOTE_EVIDENCE_ID]: {
        evidence_id: QUOTE_EVIDENCE_ID,
        producer_key: 'agent:test:quote:1',
        type: 'agent_interview',
        source: 'agent_log',
        snippet: 'Nur Snippet, kein Quote',
        source_kind: 'agent_quote',
        persona_stakeholder_group: 'Testgruppe',
      },
      [SEED_EVIDENCE_ID]: {
        evidence_id: SEED_EVIDENCE_ID,
        producer_key: 'seed:test:quote:1',
        type: 'graph_fact',
        source: 'briefing.md',
        snippet: 'Seed-Beleg für den Quote-Test.',
        source_kind: 'seed_corpus',
      },
    },
    global_evidence_refs: [],
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
                evidence_id: QUOTE_EVIDENCE_ID,
                supports_claim: true,
                match_score: 0.9,
              },
              {
                evidence_id: SEED_EVIDENCE_ID,
                supports_claim: true,
                match_score: 0.8,
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
      evidence_index: {
        ...EVIDENCE_WITH_QUOTE.evidence_index,
        [QUOTE_EVIDENCE_ID]: {
          ...EVIDENCE_WITH_QUOTE.evidence_index[QUOTE_EVIDENCE_ID],
          source_id_anchor: 'web:https://example.com/artikel',
        },
      },
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
  const C1_QUOTE_ID = 'ev_00000000000000000000000000000021'
  const C1_SEED_ID = 'ev_00000000000000000000000000000022'
  const C2_QUOTE_ID = 'ev_00000000000000000000000000000023'
  const C2_SEED_ID = 'ev_00000000000000000000000000000024'
  const VALID_EVIDENCE_WITH_SECTIONS = {
    schema_version: 3,
    report_id: 'report_test01',
    simulation_id: 'sim_test01',
    evidence_index: Object.fromEntries([
      [C1_QUOTE_ID, 'Claim 1 Quote', 'agent_quote', 'Gruppe A'],
      [C1_SEED_ID, 'Claim 1 Seed', 'seed_corpus', null],
      [C2_QUOTE_ID, 'Claim 2 Quote', 'agent_quote', 'Gruppe B'],
      [C2_SEED_ID, 'Claim 2 Seed', 'seed_corpus', null],
    ].map(([evidenceId, snippet, sourceKind, stakeholderGroup]) => [evidenceId, {
      evidence_id: evidenceId,
      producer_key: `confidence:${evidenceId}`,
      type: sourceKind === 'agent_quote' ? 'agent_interview' : 'graph_fact',
      source: sourceKind === 'agent_quote' ? 'agent_log' : 'briefing.md',
      snippet,
      source_kind: sourceKind,
      ...(stakeholderGroup ? { persona_stakeholder_group: stakeholderGroup } : {}),
    }])),
    global_evidence_refs: [],
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
                evidence_id: C1_QUOTE_ID,
                supports_claim: true,
                match_score: 0.9,
              },
              { evidence_id: C1_SEED_ID, supports_claim: true, match_score: 0.8 },
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
                evidence_id: C2_QUOTE_ID,
                supports_claim: true,
                match_score: 0.6,
              },
              { evidence_id: C2_SEED_ID, supports_claim: true, match_score: 0.7 },
            ],
            audit_trail: [{ source: 'agent_log', snippet: 'Audit B' }],
          },
        ],
      },
      {
        section_index: 3,
        section_title: 'Abschnitt 3',
        section_summary: 'Zusammenfassung 3 — spekulativer Bereich',
        // Seit #1235 (ADR-0002) braucht jeder Claim mindestens ein stützendes
        // Evidence-Item, unabhängig vom confidence_label. Eine Aussage ohne
        // stützende Evidence wird backendseitig zur Hypothese/zum Data-Gap
        // geroutet und erscheint hier folgerichtig nicht als Claim.
        claims: [],
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

// PR #975 (CodeRabbit): Die Report-Navigation darf die Registry-Run-ID nicht
// verlieren. simulation_id und run_id sind seit #764 verschieden — ohne
// ?runId=<id> faellt loadRunUsage() auf die simulationId zurueck und
// /api/runs/<id> trifft die falsche Ressource.
describe('Step4Report — runId ueberlebt die Report-Navigation (PR #975)', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    localStorageMock.clear()
    resetMockSelection()
    await router.push('/')
  })

  it('haengt die runId als Query an, wenn die Regenerierung eine neue reportId liefert', async () => {
    const wrapper = mountComponent({ simulationId: 'sim_test01', runId: 'run_registry_01' })
    await wrapper.vm.$nextTick()

    await (wrapper.vm as unknown as { regenerateWithModel: () => Promise<void> }).regenerateWithModel()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('Report')
    expect(router.currentRoute.value.params.reportId).toBe('report_test01')
    expect(router.currentRoute.value.query.runId).toBe('run_registry_01')
  })

  it('haengt die runId auch beim Report-Start an', async () => {
    const wrapper = mountComponent({ simulationId: 'sim_test01', runId: 'run_registry_02' })
    await wrapper.vm.$nextTick()

    await (wrapper.vm as unknown as { startReportConfirmed: () => Promise<void> }).startReportConfirmed()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('Report')
    expect(router.currentRoute.value.params.reportId).toBe('report_test01')
    expect(router.currentRoute.value.query.runId).toBe('run_registry_02')
  })

  it('navigiert ohne Query, wenn keine Registry-Run-ID bekannt ist', async () => {
    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await wrapper.vm.$nextTick()

    await (wrapper.vm as unknown as { regenerateWithModel: () => Promise<void> }).regenerateWithModel()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('Report')
    expect(router.currentRoute.value.query.runId).toBeUndefined()
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

  async function callRegenerate(pick?: AiModelRef): Promise<Record<string, unknown>> {
    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()
    await wrapper.vm.$nextTick()
    if (pick) {
      // Expliziter Nutzer-Pick über den Picker — kein Mount-Default.
      const controls = wrapper.findComponent({ name: 'ReportModelControls' })
      await controls.vm.$emit('update:modelValue', pick)
      await wrapper.vm.$nextTick()
    }
    await (wrapper.vm as unknown as { regenerateWithModel: () => Promise<void> }).regenerateWithModel()
    await wrapper.vm.$nextTick()
    return vi.mocked(generateReport).mock.calls.at(-1)![0] as Record<string, unknown>
  }

  it('sendet ai_model_ref und kein konkurrierendes llm_profile_id bei explizitem Pick', async () => {
    // Veraltetes Legacy-Profil im localStorage darf den Pick NICHT begleiten.
    localStorageMock.setItem('agora.report.llmProfileId', 'prof-stale')

    const payload = await callRegenerate(PICK)

    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn_minimax',
      model_id: 'MiniMax-M3',
      source: 'explicit',
    })
    expect(payload.llm_profile_id).toBeUndefined()
    expect(payload.llm_model).toBeUndefined()
  })

  it('reicht den fallback_reason des Pickers mit durch (Issue #901)', async () => {
    // AiModelPicker liefert bei einer Fallback-Auswahl einen konkreten Grund
    // (unknown_provider / provider_offline / provider_degraded). Wird er hier
    // verworfen, schreibt llm_routing_seed._fallback_reason_for den Platzhalter
    // "unspecified_fallback" in die Route — der Grund waere nur scheinbar
    // unbekannt.
    const payload = await callRegenerate({
      ...PICK,
      source: 'fallback',
      fallback_reason: 'provider_offline',
    })

    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn_minimax',
      model_id: 'MiniMax-M3',
      source: 'fallback',
      fallback_reason: 'provider_offline',
    })
  })

  it('sendet fallback_reason nicht als leeres Feld mit', async () => {
    const payload = await callRegenerate(PICK)

    expect(payload.ai_model_ref).not.toHaveProperty('fallback_reason')
  })

  it('erzeugt aus dem beim Mount übernommenen Kanon-Default KEINEN Override', async () => {
    // Kanon trägt einen Wert, aber der Nutzer hat den Picker nie angefasst.
    mockEffectiveRef.value = PICK

    const payload = await callRegenerate()

    expect(payload.ai_model_ref).toBeUndefined()
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

  // Issue #834: der v3-Profil-Legacy-Picker (Legacy-Profil-Senke) wurde
  // entfernt — es gibt keinen Fallback auf agora.report.llmProfileId mehr,
  // unabhängig vom localStorage-Inhalt. buildModelSelection() kennt nur noch
  // ai_model_ref.
  it('ignoriert das Legacy-Profil in localStorage vollständig (kein Fallback mehr)', async () => {
    localStorageMock.setItem('agora.report.llmProfileId', 'prof-legacy')

    const payload = await callRegenerate()

    expect(payload.llm_profile_id).toBeUndefined()
    expect(payload.ai_model_ref).toBeUndefined()
    expect(payload.llm_model).toBeUndefined()
    // Component liest/schreibt den Legacy-Key nicht mehr — Wert bleibt unangetastet.
    expect(localStorageMock.getItem('agora.report.llmProfileId')).toBe('prof-legacy')
  })

  it('rendert keinen Legacy-Profil-Picker mehr (Report-Profil-Block entfernt)', async () => {
    const wrapper = mountComponent({ simulationId: 'sim_test01' })
    await flushPromises()

    expect(wrapper.find('.report-profile-picker').exists()).toBe(false)
  })
})

// Issue #1023 (Befund B-26, P1): Report startete bisher ungefragt (Step3
// rief generateReport() direkt auf) und mit dem Workspace-Kanon-Default statt
// dem fuer den Lauf gewaehlten Modell. Der Bestaetigungs-Block existierte
// bereits, wurde aber nie erreicht, weil props.reportId im Normalfluss immer
// schon gesetzt war. Diese Suite deckt beide Teile ab: Bestaetigung erscheint
// auch OHNE reportId aber MIT runId (realistische run_...-UUID statt "test-id"),
// und reportRoute wird aus dem Lauf-Modell statt dem Kanon vorbelegt.
describe('Step4Report — Lauf-Modell-Vorbelegung statt Workspace-Default (#1023)', () => {
  const RUN_REGISTRY_ID = 'run_a1b2c3d4e5f6'

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

  const RUN_SNAPSHOT_ROUTING = {
    snapshots: {
      report_generation: {
        stage: 'report_generation',
        provider_id: 'conn_run_snapshot',
        model: 'run-snapshot-model',
        reasoning_effort: 'none',
        routing_version: 1,
      },
    },
    runtime_config: null,
  }

  const WORKSPACE_DEFAULT = {
    provider_connection_id: 'conn_workspace_default',
    model_id: 'workspace-default-model',
    source: 'workspace-default',
  } as AiModelRef

  function mountPending(extraProps: Record<string, unknown> = {}) {
    return mount(Step4Report, {
      props: { simulationId: 'sim_test01', runId: RUN_REGISTRY_ID, ...extraProps },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
  }

  it('zeigt den Bestaetigungs-Block auch mit gesetzter runId, solange kein reportId vorliegt', async () => {
    const wrapper = mountPending()
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="report-confirm-block"]').exists()).toBe(true)
  })

  it('uebernimmt den Snapshot der Stage report_generation als reportRoute-Default, nicht den Kanon', async () => {
    mockEffectiveRef.value = {
      provider_connection_id: 'conn_workspace_default',
      model_id: 'workspace-default-model',
      source: 'workspace-default',
    } as AiModelRef
    getRunLlmRoutingMock.mockResolvedValue({
      snapshots: {
        report_generation: {
          stage: 'report_generation',
          provider_id: 'conn_run_snapshot',
          model: 'run-snapshot-model',
          reasoning_effort: 'none',
          routing_version: 1,
        },
      },
      runtime_config: null,
    })

    const wrapper = mountPending()
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(getRunLlmRoutingMock).toHaveBeenCalledWith(RUN_REGISTRY_ID)
    const vm = wrapper.vm as unknown as { reportRoute: AiModelRef | null }
    expect(vm.reportRoute).toEqual({
      provider_connection_id: 'conn_run_snapshot',
      model_id: 'run-snapshot-model',
      source: 'explicit',
    })
  })

  it('faellt ohne Stage-Snapshot auf die vom Lauf konfigurierte Route zurueck (RuntimeLlmRouting), nicht den Kanon', async () => {
    mockEffectiveRef.value = {
      provider_connection_id: 'conn_workspace_default',
      model_id: 'workspace-default-model',
      source: 'workspace-default',
    } as AiModelRef
    getRunLlmRoutingMock.mockResolvedValue({
      snapshots: {},
      runtime_config: {
        global_default: { provider_id: 'conn_run_global', model: 'run-global-model', reasoning_effort: 'none', provider_options: {} },
        stage_overrides: {},
        routing_version: 1,
      },
    })

    const wrapper = mountPending()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const vm = wrapper.vm as unknown as { reportRoute: AiModelRef | null }
    expect(vm.reportRoute).toEqual({
      provider_connection_id: 'conn_run_global',
      model_id: 'run-global-model',
      source: 'explicit',
    })
  })

  it('faellt ohne runId auf den Workspace-Kanon zurueck (unveraendertes Verhalten)', async () => {
    mockEffectiveRef.value = {
      provider_connection_id: 'conn_workspace_default',
      model_id: 'workspace-default-model',
      source: 'workspace-default',
    } as AiModelRef

    const wrapper = mount(Step4Report, {
      props: { simulationId: 'sim_test01' },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(getRunLlmRoutingMock).not.toHaveBeenCalled()
    const vm = wrapper.vm as unknown as { reportRoute: AiModelRef | null }
    expect(vm.reportRoute).toEqual(mockEffectiveRef.value)
  })

  // PR #1025 (CodeRabbit): Die Auswertung des Lauf-Modells hing im
  // Erfolgszweig von ensureLoaded(). Schlug der Kanon-Load fehl, lief nur
  // .catch() — und das erfolgreich geladene Lauf-Modell wurde stillschweigend
  // mitverworfen, obwohl es die hoeher priorisierte Quelle ist.
  it('zeigt das Lauf-Modell auch dann, wenn der Kanon-Load fehlschlaegt', async () => {
    mockEnsureLoaded.mockRejectedValue(new Error('routing/defaults nicht erreichbar'))
    getRunLlmRoutingMock.mockResolvedValue(RUN_SNAPSHOT_ROUTING)

    const wrapper = mountPending()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const vm = wrapper.vm as unknown as { reportRoute: AiModelRef | null }
    expect(vm.reportRoute).toEqual({
      provider_connection_id: 'conn_run_snapshot',
      model_id: 'run-snapshot-model',
      source: 'explicit',
    })
  })

  // PR #1025 (Codex P1): Das Lauf-Modell wurde nur angezeigt.
  // start_generation() legt aber einen neuen Report-Lauf an und seedet ihn aus
  // dem Request — ohne ai_model_ref lief der Report unter dem
  // Workspace-Default, waehrend Anzeige und Start-Log das Lauf-Modell nannten.
  it('sendet das Lauf-Modell als ai_model_ref, auch ohne Picker-Interaktion', async () => {
    mockEffectiveRef.value = WORKSPACE_DEFAULT
    getRunLlmRoutingMock.mockResolvedValue(RUN_SNAPSHOT_ROUTING)

    const wrapper = mountPending()
    await flushPromises()
    await wrapper.vm.$nextTick()
    await (wrapper.vm as unknown as { startReportConfirmed: () => Promise<void> }).startReportConfirmed()
    await wrapper.vm.$nextTick()

    const payload = vi.mocked(generateReport).mock.calls.at(-1)![0] as Record<string, unknown>
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn_run_snapshot',
      model_id: 'run-snapshot-model',
      source: 'run-override',
    })
  })

  it('sendet keinen ai_model_ref, wenn nur der Workspace-Kanon die Anzeige belegt', async () => {
    // Gegenstueck zum Test darueber: der Kanon-Default bleibt ein reiner
    // Anzeigewert. Ihn mitzuschicken wuerde die serverseitigen
    // Stage-Defaults ueberschreiben, obwohl der Nutzer nichts gewaehlt hat.
    mockEffectiveRef.value = WORKSPACE_DEFAULT

    const wrapper = mount(Step4Report, {
      props: { simulationId: 'sim_test01' },
      global: { plugins: [router, i18n], stubs: globalStubs },
    })
    await flushPromises()
    await wrapper.vm.$nextTick()
    await (wrapper.vm as unknown as { startReportConfirmed: () => Promise<void> }).startReportConfirmed()
    await wrapper.vm.$nextTick()

    const payload = vi.mocked(generateReport).mock.calls.at(-1)![0] as Record<string, unknown>
    expect(payload.ai_model_ref).toBeUndefined()
  })

  it('laesst den Picker-Pick gegen das Lauf-Modell gewinnen', async () => {
    mockEffectiveRef.value = WORKSPACE_DEFAULT
    getRunLlmRoutingMock.mockResolvedValue(RUN_SNAPSHOT_ROUTING)

    const wrapper = mountPending()
    await flushPromises()
    await wrapper.vm.$nextTick()

    const controls = wrapper.findComponent({ name: 'ReportModelControls' })
    await controls.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn_picked',
      model_id: 'picked-model',
      source: 'explicit',
    } as AiModelRef)
    await wrapper.vm.$nextTick()

    await (wrapper.vm as unknown as { startReportConfirmed: () => Promise<void> }).startReportConfirmed()
    await wrapper.vm.$nextTick()

    const payload = vi.mocked(generateReport).mock.calls.at(-1)![0] as Record<string, unknown>
    expect(payload.ai_model_ref).toEqual({
      provider_connection_id: 'conn_picked',
      model_id: 'picked-model',
      source: 'explicit',
    })
  })
})

// Issue #1023 (Befund B-17, P2): pollStatus() verschluckte Transportfehler
// (`catch { /* swallow */ }`) ohne Retry-Zaehler — der Nutzer wartete auf ein
// Ergebnis, das laengst nicht mehr zustande kommen konnte. Der Defekt zeigt
// sich nur ueber eine FOLGE fehlgeschlagener Polls, nicht in einem
// Einzelzustand (genau die Luecke aus #961/#966/#985).
//
// Issue #1206: die Zaehl-Semantik selbst liegt jetzt in
// composables/__tests__/useReportGeneration.spec.ts und wird dort direkt
// ueber das Interface geprueft. Hier bleibt, was nur ein Mount zeigen kann:
// dass der gezaehlte Zustand tatsaechlich im DOM ankommt. Die Poll-Folge
// entsteht dafuer ueber den echten Timer-Loop statt ueber einen Aufruf des
// komponenteninternen pollStatus() — vorher war das eine Kopplung an ein
// Internum, das es nicht mehr gibt.
describe('Step4Report — Poll-Transportfehler werden gezaehlt statt verschluckt (#1023, Befund B-17)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
    resetMockSelection()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  const transportErrorVisible = (wrapper: ReturnType<typeof mountComponent>) =>
    wrapper.find('[data-testid="report-poll-transport-error"]').exists()

  it('zeigt den Transportfehler-Hinweis erst nach 3 aufeinanderfolgenden Fehlschlaegen, nicht bei einem einzelnen', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'))

    const wrapper = mountComponent()
    // onMounted pollt einmal — Fehlschlag #1.
    await vi.advanceTimersByTimeAsync(0)
    await wrapper.vm.$nextTick()
    expect(transportErrorVisible(wrapper)).toBe(false)

    // Fehlschlag #2 aus dem laufenden Poll-Intervall.
    await vi.advanceTimersByTimeAsync(REPORT_STATUS_POLL_INTERVAL_MS)
    await wrapper.vm.$nextTick()
    expect(transportErrorVisible(wrapper)).toBe(false)

    // Fehlschlag #3 — Schwelle erreicht.
    await vi.advanceTimersByTimeAsync(REPORT_STATUS_POLL_INTERVAL_MS)
    await wrapper.vm.$nextTick()
    expect(transportErrorVisible(wrapper)).toBe(true)
  })

  it('heilt den Transportfehler-Hinweis aus, sobald ein Poll wieder erfolgreich ist', async () => {
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'))

    const wrapper = mountComponent()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(REPORT_STATUS_POLL_INTERVAL_MS)
    await vi.advanceTimersByTimeAsync(REPORT_STATUS_POLL_INTERVAL_MS)
    await wrapper.vm.$nextTick()
    expect(transportErrorVisible(wrapper)).toBe(true)

    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      success: true,
      data: { status: 'planning', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    await vi.advanceTimersByTimeAsync(REPORT_STATUS_POLL_INTERVAL_MS)
    await wrapper.vm.$nextTick()
    expect(transportErrorVisible(wrapper)).toBe(false)
  })
})

// Issue #1188 (Nachbesserung): 15s Gesamtbudget (5x alle 3s) verfehlte das
// reale Zeitfenster aus Issue #1187 (bis zu 1344s Nachbearbeitung) um zwei
// Groessenordnungen. Belegt: solange der Lauf terminal ist und die
// Evidenzkarte trotzdem fehlt, retried Step4Report.vue mit Backoff
// (3s → 30s gedeckelt) ueber ein 10-Minuten-Budget, bevor der Button auf
// "nicht verfuegbar" statt "wird noch erzeugt" umspringt.
describe('Step4Report — Evidence-Retry-Budget nach Laufende (#1188, Nachbesserung)', () => {
  const evidenceI18n = createI18n({ legacy: false, locale: 'de', messages: { de: deMessages } })

  beforeEach(() => {
    vi.clearAllMocks()
    resetMockSelection()
    ;(getReportStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_test01', simulation_id: 'sim_test01' },
    })
    ;(getReport as ReturnType<typeof vi.fn>).mockResolvedValue({ success: true, data: VALID_REPORT })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('haelt den Button auf "wird noch erzeugt", solange das 10-Minuten-Budget nicht ausgeschoepft ist, und wechselt danach auf "nicht verfuegbar"', async () => {
    vi.useFakeTimers()
    ;(getReportEvidence as ReturnType<typeof vi.fn>).mockResolvedValue({ success: false })

    const wrapper = mount(Step4Report, {
      props: { reportId: 'report_test01' },
      global: { plugins: [router, evidenceI18n], stubs: globalStubs },
    })
    await flushPromises()

    const desc = () => wrapper.find('[data-testid="evidence-export-pending-desc"]')
    expect(desc().exists()).toBe(true)
    expect(desc().text()).toBe(deMessages.step4.export.evidencePending)

    // Kurz nach dem ersten Fehlschlag (< 10 Minuten Budget) bleibt der Text
    // "wird noch erzeugt" — kein vorzeitiges Aufgeben mehr wie beim alten
    // 15s-Budget.
    await vi.advanceTimersByTimeAsync(20000)
    await flushPromises()
    expect(desc().exists()).toBe(true)
    expect(desc().text()).toBe(deMessages.step4.export.evidencePending)

    // Budget (10 Minuten) ueberschreiten: der Text muss auf "nicht
    // verfuegbar" wechseln, sonst behauptet die UI faelschlich, die Karte
    // sei noch unterwegs.
    await vi.advanceTimersByTimeAsync(650000)
    await flushPromises()
    await wrapper.vm.$nextTick()

    expect(desc().exists()).toBe(true)
    expect(desc().text()).toBe(deMessages.step4.export.evidenceUnavailable)
  })
})
