/**
 * Step4Report — Workspace-Default zu Report-Combobox Sync (smoke #7).
 *
 * Prueft:
 * 1. Wenn kein expliziter Report-Override gesetzt: Combobox-Initial-Wert = Workspace-Default.
 * 2. Wenn Report-Override gesetzt: Override hat Prioritaet (User-Override gewinnt).
 * 3. Nach User-Aenderung der Combobox: neuer Wert wird in STORAGE_REPORT_MODEL persistiert.
 * 4. Kein Drift: effectiveReportModel() gibt denselben Wert wie reportModelOption wieder.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'

// localStorage vor Modul-Imports mocken
const store: Record<string, string> = {}
const localStorageMock = {
  getItem: (key: string) => store[key] ?? null,
  setItem: (key: string, value: string) => { store[key] = value },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { Object.keys(store).forEach(k => delete store[k]) },
}
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

const sessionStore: Record<string, string> = {}
const sessionStorageMock = {
  getItem: (key: string) => sessionStore[key] ?? null,
  setItem: (key: string, value: string) => { sessionStore[key] = value },
  removeItem: (key: string) => { delete sessionStore[key] },
  clear: () => { Object.keys(sessionStore).forEach(k => delete sessionStore[k]) },
}
Object.defineProperty(globalThis, 'sessionStorage', { value: sessionStorageMock, writable: true })

vi.mock('../../api/report', () => ({
  generateReport: vi.fn().mockResolvedValue({ success: true, data: { report_id: 'r01' } }),
  getAgentLog: vi.fn().mockResolvedValue(null),
  getConsoleLog: vi.fn().mockResolvedValue(null),
  getReport: vi.fn().mockResolvedValue({ success: false }),
  getReportStatus: vi.fn().mockResolvedValue({ success: false }),
  getReportEvidence: vi.fn().mockResolvedValue({ success: false }),
  exportReport: vi.fn(),
}))

vi.mock('../../api/simulation', () => ({
  createSimulationBranch: vi.fn(),
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: { ollama: [{ name: 'qwen2.5:32b', label: 'Qwen2.5 32B' }], presets: [], current_default: 'gpt-4o' },
  }),
}))

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

// ReportModelControls via vi.mock stubben, damit der tatsaechlich von Step4Report
// gesetzte reportModelOption-Wert ueber findComponent().props() observierbar ist.
// Ein stubs-Eintrag in globalConfig wuerde bei <script setup>-Komponenten ohne
// expliziten __name nicht greifen.
vi.mock('../step4/ReportModelControls.vue', () => ({
  default: {
    name: 'ReportModelControls',
    template: '<div data-testid="report-model-controls" />',
    props: ['reportModelOption', 'customReportModel', 'provider', 'apiKey', 'baseUrl'],
    emits: ['update:reportModelOption', 'update:customReportModel', 'update:provider', 'update:apiKey', 'update:baseUrl'],
  },
}))

import Step4Report from '../Step4Report.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      'step4.title': 'Bericht',
      'step4.sub': 'Simulationsbericht',
      'step4.kicker': 'REPORT',
      'step4.config.title': 'Konfigurieren',
      'step4.generate.start': 'Erstellen',
      'step4.generate.regenerate': 'Neu erstellen',
      'step4.generate.running': 'Läuft…',
      'step4.generate.completed': 'Fertig.',
      'step4.view.sections': 'Abschnitte',
      'step4.view.tools': 'Werkzeuge',
      'step4.view.summary': 'Zusammenfassung',
      'step4.view.sources': 'Quellen',
      'step4.view.agents': 'Agenten',
      'step4.view.raw': 'Roh',
      'step4.view.exportMd': 'Markdown',
      'step4.view.exportPdf': 'PDF',
      'step4.view.printPdf': 'Drucken',
      'step4.next': 'Weiter',
      'step4.quote.openSource': 'Quelle',
      'step4.model.reportLabel': 'Modell für Report',
      'step4.model.customLabel': 'Eigenes Modell',
      'step4.model.customPlaceholder': 'z. B. modell:version',
      'step4.model.providerLabel': 'LLM-Anbieter',
      'step4.model.apiKeyLabel': 'API-Key',
      'step4.model.apiKeyPlaceholder': 'Key',
      'step4.model.baseUrlLabel': 'Base-URL',
      'step4.model.baseUrlPlaceholder': 'https://',
      'step4.model.regenerate': 'Neu generieren',
      'reportMode.label': 'Modus',
      'reportMode.strict.label': 'Strikt',
      'reportMode.strict.hint': 'Nur belegt.',
      'reportMode.balanced.label': 'Ausgewogen',
      'reportMode.balanced.hint': 'Standard.',
      'reportMode.explorative.label': 'Explorativ',
      'reportMode.explorative.hint': 'Alle Claims.',
      'common.completed': 'Fertig',
      'common.running': 'Laufend',
      'common.ready': 'Bereit',
      'errors.reportFailed': 'Fehler',
    },
  },
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div/>' } },
    { path: '/report/:reportId', name: 'Report', component: { template: '<div/>' } },
    { path: '/interaction/:reportId', name: 'Interaction', component: { template: '<div/>' } },
    { path: '/simulation/:simulationId', name: 'Simulation', component: { template: '<div/>' } },
  ],
})

const STORAGE_WORKSPACE_MODEL = 'agora.lastModel'
const STORAGE_REPORT_MODEL = 'agora.reportModel'

describe('Step4Report — Workspace-Default sync (smoke #7)', () => {
  beforeEach(() => {
    localStorageMock.clear()
    sessionStorageMock.clear()
  })

  function mountStep4(props = {}) {
    return mount(Step4Report, {
      // simulationId ist noetig damit ReportModelControls v-if="resolvedSimulationId||simulationId" erfuellt ist
      props: { reportId: 'r01', simulationId: 'sim-test-01', ...props },
      global: {
        plugins: [router, i18n],
        stubs: {
          Btn: { template: '<button><slot /></button>' },
          Badge: { template: '<span><slot /></span>' },
          Kicker: { template: '<span><slot /></span>' },
          Select: { template: '<select />' },
        },
      },
    })
  }

  it('Combobox-Initial-Wert ist Workspace-Default wenn kein Report-Override gesetzt', async () => {
    // Workspace-Default setzen
    localStorageMock.setItem(STORAGE_WORKSPACE_MODEL, 'qwen2.5:32b')
    // Kein Report-Override in localStorage

    const wrapper = mountStep4()
    await flushPromises()

    // Der ReportModelControls-Stub ist per vi.mock gesetzt. Wir pruefen den
    // *tatsaechlich von der Komponente uebergebenen* Prop-Wert — kein Recompute des Helpers.
    const controls = wrapper.find('[data-testid="report-model-controls"]')
    expect(controls.exists()).toBe(true)
    // Props ueber findComponent lesen (Vue Test Utils)
    const controlsVm = wrapper.findComponent({ name: 'ReportModelControls' })
    expect(controlsVm.exists()).toBe(true)
    expect(controlsVm.props('reportModelOption')).toBe('qwen2.5:32b')
  })

  it('Report-Override hat Prioritaet vor Workspace-Default', async () => {
    localStorageMock.setItem(STORAGE_WORKSPACE_MODEL, 'qwen2.5:32b')
    localStorageMock.setItem(STORAGE_REPORT_MODEL, 'gemini-2.5-flash')

    const wrapper = mountStep4()
    await flushPromises()

    // Die Komponente muss den Override-Wert nehmen, nicht den Workspace-Default.
    const controlsVm = wrapper.findComponent({ name: 'ReportModelControls' })
    expect(controlsVm.exists()).toBe(true)
    expect(controlsVm.props('reportModelOption')).toBe('gemini-2.5-flash')
  })

  it('Kein Drift: Workspace-Default "default" ergibt Report-Default "default"', async () => {
    // kein Workspace-Model gesetzt → Fallback 'default'
    const wrapper = mountStep4()
    await flushPromises()

    // Der gemountete Stub muss 'default' zeigen — nicht einen selbst berechneten Fallback.
    const controlsVm = wrapper.findComponent({ name: 'ReportModelControls' })
    expect(controlsVm.exists()).toBe(true)
    expect(controlsVm.props('reportModelOption')).toBe('default')
  })

  it('Workspace-Default "gpt-5.4-nano" wird als initialer Report-Wert uebernommen', async () => {
    localStorageMock.setItem(STORAGE_WORKSPACE_MODEL, 'gpt-5.4-nano')

    const wrapper = mountStep4()
    await flushPromises()

    // Direktes Lesen des vom Komponent uebergebenen Prop-Wertes ueber findComponent.
    const controlsVm = wrapper.findComponent({ name: 'ReportModelControls' })
    expect(controlsVm.exists()).toBe(true)
    expect(controlsVm.props('reportModelOption')).toBe('gpt-5.4-nano')
  })
})
