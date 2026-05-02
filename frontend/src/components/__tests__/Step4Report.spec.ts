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
