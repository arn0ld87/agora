// Issue #1206 — Interface-Tests der Report-Statusmaschine.
//
// Bewusst ohne `mount()` und ohne `vi.mock`: das Options-Objekt liefert die
// gesamte Umgebung (HTTP-Seam, i18n, Log-Senke, Modellauswahl, Navigation,
// Begleit-Polls), also ist das zurueckgegebene Interface die Testflaeche.
// Vorbild fuer den Schnitt: contracts/__tests__/runParamsQuery.spec.ts.
//
// Vorher war dieser Flow nur ueber einen Mount von Step4Report.vue plus
// sechzehn Modul-Mocks beobachtbar — entsprechend hat jede Aenderung an der
// Statusmaschine die 1754-Zeilen-Komponenten-Spec mitgezogen.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  useReportGeneration,
  REPORT_POLL_FAILURE_THRESHOLD,
  type UseReportGenerationOptions,
  type UseReportGenerationReturn,
} from '../useReportGeneration'
import type { GenerateReportData } from '../../api/report'
import type { Report } from '../../contracts/reportContract'

const VALID_REPORT: Report = {
  schema_version: 2,
  report_id: 'report_1',
  simulation_id: 'sim_1',
  graph_id: 'graph_1',
  simulation_requirement: 'Testanforderung',
  status: 'completed',
  markdown_content: '# Bericht',
  missing_sections: [],
  has_evidence: false,
  red_team_findings: [],
  evidence_sections: 0,
  run_degradations: [],
}

const VALID_OUTLINE = {
  title: 'Berichtstitel',
  summary: 'Zusammenfassung',
  sections: [{ title: 'Abschnitt A', description: 'Beschreibung A' }],
}

function makeLogStream() {
  return {
    polling: {
      start: vi.fn(async () => {}),
      stop: vi.fn(() => {}),
    },
    reset: vi.fn(() => {}),
  }
}

function makeApi() {
  return {
    generateReport: vi
      .fn<(data: GenerateReportData) => Promise<unknown>>()
      .mockResolvedValue({ success: true, data: { report_id: 'report_neu' } }),
    getReport: vi
      .fn<(reportId: string) => Promise<unknown>>()
      .mockResolvedValue({ success: true, data: VALID_REPORT }),
    getReportStatus: vi
      .fn<(params: { simulationId?: string; reportId?: string }) => Promise<unknown>>()
      .mockResolvedValue({ success: true, data: { status: 'generating' } }),
  }
}

interface Harness {
  generation: UseReportGenerationReturn
  api: ReturnType<typeof makeApi>
  addLog: ReturnType<typeof vi.fn>
  onLifecycleChange: ReturnType<typeof vi.fn>
  recordSchemaError: ReturnType<typeof vi.fn>
  loadEvidence: ReturnType<typeof vi.fn>
  onStarted: ReturnType<typeof vi.fn>
  logStream: ReturnType<typeof makeLogStream>
}

/**
 * Ohne Komponente feuert das `onUnmounted`-Cleanup von `usePolling` nie — die
 * laufende Statusabfrage muss deshalb nach jedem Test von Hand gestoppt
 * werden, sonst pollen Intervalle vergangener Tests in spaetere hinein.
 * Fake-Timer als zweite Absicherung: so entsteht gar kein echtes Intervall.
 */
const activeGenerations: UseReportGenerationReturn[] = []

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
})

afterEach(() => {
  while (activeGenerations.length) activeGenerations.pop()!.stop()
  vi.useRealTimers()
})

function setup(overrides: Partial<UseReportGenerationOptions> = {}): Harness {
  const api = {
    generateReport: vi.fn().mockResolvedValue({ success: true, data: { report_id: 'report_neu' } }),
    getReport: vi.fn().mockResolvedValue({ success: true, data: VALID_REPORT }),
    getReportStatus: vi.fn().mockResolvedValue({ success: true, data: { status: 'generating' } }),
  }
  const addLog = vi.fn()
  const onLifecycleChange = vi.fn()
  const recordSchemaError = vi.fn()
  const loadEvidence = vi.fn().mockResolvedValue(undefined)
  const onStarted = vi.fn()
  const logStream = makeLogStream()

  const generation = useReportGeneration({
    reportId: () => 'report_1',
    simulationId: () => 'sim_1',
    // Identitaets-Uebersetzer: der Test prueft, DASS ein Schluessel gemeldet
    // wird, nicht wie de.json ihn gerade formuliert.
    t: (key) => key,
    addLog,
    onLifecycleChange,
    recordSchemaError,
    loadEvidence,
    buildRequestOptions: () => ({ mode: 'balanced' }),
    onStarted,
    logStreams: [logStream],
    api,
    ...overrides,
  })
  activeGenerations.push(generation)

  return { generation, api, addLog, onLifecycleChange, recordSchemaError, loadEvidence, onStarted, logStream }
}

describe('useReportGeneration — bootstrap()', () => {
  it('fordert ohne Report-ID die Startbestaetigung an, statt zu pollen', async () => {
    const h = setup({ reportId: () => undefined, simulationId: () => 'sim_1' })

    await h.generation.bootstrap()

    expect(h.generation.status.phase.value).toBe(0)
    expect(h.generation.status.pending.value).toBe(true)
    expect(h.logStream.polling.start).not.toHaveBeenCalled()
  })

  it('fragt ohne jede ID gar nicht erst beim Backend nach', async () => {
    const h = setup({ reportId: () => undefined, simulationId: () => undefined })

    await h.generation.bootstrap()

    expect(h.api.getReportStatus).not.toHaveBeenCalled()
  })

  it('nimmt bei laufendem Report das Polling inklusive Begleit-Polls auf', async () => {
    const h = setup()

    await h.generation.bootstrap()

    expect(h.generation.status.phase.value).toBe(1)
    expect(h.generation.status.backendStatus.value).toBe('generating')
    expect(h.logStream.polling.start).toHaveBeenCalledTimes(1)
  })

  it('laedt den Report nach, wenn die Ansicht auf einem bereits fertigen Lauf betreten wird', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_1' },
    })

    await h.generation.bootstrap()

    expect(h.generation.status.isComplete.value).toBe(true)
    expect(h.generation.status.phase.value).toBe(2)
    expect(h.generation.report.full.value?.report_id).toBe('report_1')
    // Terminal erreicht: die Begleit-Polls duerfen nicht weiterlaufen.
    expect(h.logStream.polling.stop).toHaveBeenCalled()
  })
})

describe('useReportGeneration — Endzustaende', () => {
  it('meldet completed, laedt Report und Evidenzkarte und beendet das Polling', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_1', simulation_id: 'sim_x' },
    })

    await h.generation.bootstrap()

    expect(h.onLifecycleChange).toHaveBeenCalledWith('completed')
    expect(h.api.getReport).toHaveBeenCalledWith('report_1')
    expect(h.loadEvidence).toHaveBeenCalledTimes(1)
    expect(h.generation.report.resolvedSimulationId.value).toBe('sim_1')
  })

  it('meldet incomplete als eigenen Endzustand mit Nutzerhinweis', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'incomplete', report_id: 'report_1' },
    })

    await h.generation.bootstrap()

    expect(h.onLifecycleChange).toHaveBeenCalledWith('incomplete')
    expect(h.addLog).toHaveBeenCalledWith('step4.status.incomplete')
    // Der Rest des Reports bleibt nutzbar — er wird trotzdem geladen.
    expect(h.api.getReport).toHaveBeenCalledWith('report_1')
    expect(h.generation.status.isComplete.value).toBe(true)
  })

  it('meldet failed terminal und beendet das Polling', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'failed', error: 'LLM-Timeout' },
    })

    await h.generation.bootstrap()

    expect(h.onLifecycleChange).toHaveBeenCalledWith('error')
    expect(h.addLog).toHaveBeenCalledWith('errors.reportFailed: LLM-Timeout')
    expect(h.generation.status.phase.value).toBe(2)
    expect(h.generation.status.isComplete.value).toBe(true)
    expect(h.logStream.polling.stop).toHaveBeenCalled()
  })

  it('sperrt nach einem Endzustand den erneuten Einstieg ins Polling', async () => {
    // isComplete ist zugleich die Reload-Sperre: ein zweites bootstrap() darf
    // den erreichten Endzustand nicht durch "laeuft gerade" ersetzen.
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'failed', error: 'LLM-Timeout' },
    })
    await h.generation.bootstrap()
    h.logStream.polling.start.mockClear()

    await h.generation.bootstrap()

    expect(h.generation.status.phase.value).toBe(2)
    expect(h.logStream.polling.start).not.toHaveBeenCalled()
  })

  it('meldet einen Schema-Mismatch des Reports, statt kaputte Daten zu halten', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_1' },
    })
    h.api.getReport.mockResolvedValue({ success: true, data: { schema_version: 99 } })

    await h.generation.bootstrap()

    expect(h.recordSchemaError).toHaveBeenCalledWith('report', expect.anything())
    expect(h.generation.report.full.value).toBeNull()
    // Die Evidenzkarte wird trotz Report-Mismatch angefordert.
    expect(h.loadEvidence).toHaveBeenCalled()
  })

  it('laedt keinen Report nach, wenn der Endzustand ohne Report-ID kommt', async () => {
    // Die Statusabfrage kommt auch mit reiner Simulations-ID durch. Fehlt in
    // der Antwort dann `report_id`, gibt es nichts nachzuladen — ein
    // getReport(undefined) landete still im leeren catch (CodeRabbit, PR #1207).
    const h = setup({ reportId: () => undefined, simulationId: () => 'sim_1' })
    h.api.getReportStatus.mockResolvedValue({ success: true, data: { status: 'completed' } })

    await h.generation.bootstrap()

    expect(h.generation.status.isComplete.value).toBe(true)
    expect(h.api.getReport).not.toHaveBeenCalled()
  })

  it('zieht die Outline aus dem Report nach, wenn der Status keine liefert (#739)', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'completed', report_id: 'report_1' },
    })
    h.api.getReport.mockResolvedValue({
      success: true,
      data: { ...VALID_REPORT, outline: VALID_OUTLINE },
    })

    await h.generation.bootstrap()

    expect(h.generation.progress.outline.value?.title).toBe('Berichtstitel')
  })
})

// Issue #1023 (Befund B-17): der Defekt zeigt sich nur ueber eine FOLGE
// fehlgeschlagener Polls, nie in einem Einzelzustand — genau die Luecke, an
// der #961/#966/#985 nacheinander vorbeigezielt haben.
describe('useReportGeneration — Transportfehler (#1023, Befund B-17)', () => {
  it('meldet den Transportfehler erst beim Erreichen der Schwelle', async () => {
    const h = setup()
    h.api.getReportStatus.mockRejectedValue(new Error('network down'))

    for (let i = 1; i < REPORT_POLL_FAILURE_THRESHOLD; i++) {
      await h.generation.bootstrap()
      expect(h.generation.status.transportError.value).toBe(false)
    }

    await h.generation.bootstrap()

    expect(h.generation.status.failureCount.value).toBe(REPORT_POLL_FAILURE_THRESHOLD)
    expect(h.generation.status.transportError.value).toBe(true)
    expect(h.addLog).toHaveBeenCalledWith('step4.status.pollTransportError')
  })

  it('loggt nach der Schwelle nicht bei jedem weiteren Fehlschlag erneut', async () => {
    const h = setup()
    h.api.getReportStatus.mockRejectedValue(new Error('network down'))

    for (let i = 0; i < REPORT_POLL_FAILURE_THRESHOLD + 3; i++) {
      await h.generation.bootstrap()
    }

    const transportLogs = h.addLog.mock.calls.filter(
      ([message]) => message === 'step4.status.pollTransportError'
    )
    expect(transportLogs).toHaveLength(1)
  })

  it('heilt aus, sobald ein Poll wieder durchkommt', async () => {
    const h = setup()
    h.api.getReportStatus.mockRejectedValue(new Error('network down'))
    for (let i = 0; i < REPORT_POLL_FAILURE_THRESHOLD; i++) await h.generation.bootstrap()
    expect(h.generation.status.transportError.value).toBe(true)

    h.api.getReportStatus.mockResolvedValue({ success: true, data: { status: 'generating' } })
    await h.generation.bootstrap()

    expect(h.generation.status.transportError.value).toBe(false)
    expect(h.generation.status.failureCount.value).toBe(0)
  })
})

describe('useReportGeneration — start() und regenerate()', () => {
  it('startet ohne force_regenerate und uebernimmt Modus und Modellauswahl', async () => {
    const h = setup({
      buildRequestOptions: () => ({
        mode: 'strict',
        ai_model_ref: { provider_connection_id: 'conn_1', model_id: 'modell-a', source: 'explicit' },
      }),
      describeModel: () => 'modell-a',
    })

    await h.generation.start()

    const payload = h.api.generateReport.mock.calls.at(-1)![0]
    expect(payload).toEqual({
      simulation_id: 'sim_1',
      mode: 'strict',
      ai_model_ref: { provider_connection_id: 'conn_1', model_id: 'modell-a', source: 'explicit' },
    })
    expect(payload).not.toHaveProperty('force_regenerate')
    expect(h.addLog).toHaveBeenCalledWith('Report starten mit modell-a (Modus: strict)…')
  })

  it('setzt Fortschritt und Begleit-Polls zurueck und meldet die neue Report-ID', async () => {
    const h = setup()
    h.api.getReportStatus.mockResolvedValue({
      success: true,
      data: { status: 'generating', sections: { intro: {} }, current_section_index: 2 },
    })
    await h.generation.bootstrap()
    expect(h.generation.progress.currentSectionIndex.value).toBe(2)

    await h.generation.start()

    expect(h.generation.progress.currentSectionIndex.value).toBeNull()
    expect(h.generation.progress.sections.value).toEqual({})
    expect(h.generation.report.full.value).toBeNull()
    expect(h.logStream.reset).toHaveBeenCalledTimes(1)
    expect(h.onLifecycleChange).toHaveBeenCalledWith('processing')
    expect(h.onStarted).toHaveBeenCalledWith('report_neu')
    expect(h.generation.status.phase.value).toBe(1)
  })

  it('wirft den Nutzer bei einem fehlgeschlagenen Start in die Bestaetigung zurueck', async () => {
    const h = setup()
    h.api.generateReport.mockResolvedValue({ success: false, error: 'kein Kontingent' })

    await h.generation.start()

    expect(h.addLog).toHaveBeenCalledWith('Fehler: kein Kontingent')
    expect(h.generation.status.pending.value).toBe(true)
    expect(h.generation.status.isBusy.value).toBe(false)
    expect(h.onStarted).not.toHaveBeenCalled()
  })

  it('startet ohne Simulations-ID gar nicht erst', async () => {
    const h = setup({ reportId: () => undefined, simulationId: () => undefined })

    await h.generation.start()

    expect(h.api.generateReport).not.toHaveBeenCalled()
    expect(h.addLog).toHaveBeenCalledWith('simulationId fehlt — Report-Start nicht möglich.')
  })

  it('regeneriert mit force_regenerate', async () => {
    const h = setup()

    await h.generation.regenerate()

    expect(h.api.generateReport.mock.calls.at(-1)![0]).toMatchObject({
      simulation_id: 'sim_1',
      force_regenerate: true,
      mode: 'balanced',
    })
    expect(h.addLog).toHaveBeenCalledWith('Report neu generieren (Modus: balanced)…')
  })

  it('laesst die Startbestaetigung beim Regenerieren unangetastet — es steht bereits ein Report', async () => {
    const h = setup()
    h.api.generateReport.mockResolvedValue({ success: false, error: 'kaputt' })

    await h.generation.regenerate()

    expect(h.generation.status.pending.value).toBe(false)
  })

  it('faengt einen Transportfehler beim Start ab, ohne den Aufrufer zu werfen', async () => {
    const h = setup()
    h.api.generateReport.mockRejectedValue(new Error('backend weg'))

    await expect(h.generation.start()).resolves.toBeUndefined()

    expect(h.addLog).toHaveBeenCalledWith('backend weg')
    expect(h.generation.status.pending.value).toBe(true)
    expect(h.generation.status.isBusy.value).toBe(false)
  })
})

describe('useReportGeneration — stop()', () => {
  it('haelt die Begleit-Polls mit an', async () => {
    const h = setup()
    await h.generation.bootstrap()

    h.generation.stop()

    expect(h.logStream.polling.stop).toHaveBeenCalled()
  })
})
