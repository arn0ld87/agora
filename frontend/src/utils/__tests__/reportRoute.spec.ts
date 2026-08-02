import { describe, it, expect } from 'vitest'

import {
  buildReportRoute,
  buildInteractionRoute,
  buildReportReadyRoute,
  INTERACTION_SIMULATION_ID_QUERY_KEY,
  PENDING_REPORT_ID,
  REPORT_SIMULATION_ID_QUERY_KEY,
} from '../reportRoute'

describe('buildReportRoute', () => {
  it('haengt die runId als Query an, wenn sie bekannt ist', () => {
    // PR #975 (CodeRabbit): Ohne den Query verliert StepReportView beim
    // Wechsel auf die neue reportId die Registry-Run-ID und Step4Report
    // faellt auf simulationId zurueck — /api/runs/<id> braucht aber die
    // Run-Registry-ID.
    expect(buildReportRoute('rep-1', 'run-42')).toEqual({
      name: 'Report',
      params: { reportId: 'rep-1' },
      query: { runId: 'run-42' },
    })
  })

  it('laesst den Query weg, wenn keine runId vorliegt', () => {
    // Direktaufruf der Report-Route ohne ?runId — die Legacy-Aufloesung
    // ueber simulationId bleibt aktiv, ein leerer Query-Key wuerde sie
    // nur verschleiern.
    expect(buildReportRoute('rep-1')).toEqual({
      name: 'Report',
      params: { reportId: 'rep-1' },
    })
  })

  it('behandelt leere Strings wie fehlende runId', () => {
    expect(buildReportRoute('rep-1', '')).toEqual({
      name: 'Report',
      params: { reportId: 'rep-1' },
    })
  })
})

// Issue #1023 (Regression aus PR #997): ?runId= transportierte auf der
// Interaktions-Route faelschlich denselben Wert wie auf der Report-Route,
// obwohl dort eine Simulation-ID (sim_...) statt einer Registry-Run-ID
// (run_...) noetig ist. buildInteractionRoute nimmt deshalb einen eigenen
// Query-Schluessel und laesst nur ein gueltiges sim_...-Format durch.
describe('buildInteractionRoute', () => {
  it('haengt eine gueltige Simulation-ID unter einem eigenen Query-Schluessel an', () => {
    expect(buildInteractionRoute('rpt-1', 'sim_28a4367b2937')).toEqual({
      name: 'Interaction',
      params: { reportId: 'rpt-1' },
      query: { [INTERACTION_SIMULATION_ID_QUERY_KEY]: 'sim_28a4367b2937' },
    })
  })

  it('verwirft eine Registry-Run-ID (run_...) statt sie als Simulation-ID durchzureichen', () => {
    // Realistische Registry-UUID, wie sie run_registry.py vergibt
    // (f"run_{uuid.uuid4().hex[:12]}").
    expect(buildInteractionRoute('rpt-1', 'run_a1b2c3d4e5f6')).toEqual({
      name: 'Interaction',
      params: { reportId: 'rpt-1' },
    })
  })

  it('laesst den Query weg, wenn keine Simulation-ID vorliegt', () => {
    expect(buildInteractionRoute('rpt-1')).toEqual({
      name: 'Interaction',
      params: { reportId: 'rpt-1' },
    })
  })
})

// Issue #1023 (Befund B-26, P1): Schritt 3 ruft nicht mehr generateReport()
// direkt auf, sondern navigiert in einen "bereit"-Zustand. Die Report-Route
// verlangt zwingend einen :reportId-Pfad-Parameter — der Sentinel 'new'
// spiegelt die Konvention aus useGraphBuildPipeline.ts (currentProjectId
// === 'new').
describe('buildReportReadyRoute', () => {
  it('nutzt den Sentinel-reportId "new" und haengt simulationId + runId als Query an', () => {
    expect(buildReportReadyRoute({ runId: 'run_a1b2c3d4e5f6', simulationId: 'sim_test01' })).toEqual({
      name: 'Report',
      params: { reportId: PENDING_REPORT_ID },
      query: { [REPORT_SIMULATION_ID_QUERY_KEY]: 'sim_test01', runId: 'run_a1b2c3d4e5f6' },
    })
  })

  it('laesst runId im Query weg, wenn keine Registry-Run-ID vorliegt', () => {
    expect(buildReportReadyRoute({ simulationId: 'sim_test01' })).toEqual({
      name: 'Report',
      params: { reportId: PENDING_REPORT_ID },
      query: { [REPORT_SIMULATION_ID_QUERY_KEY]: 'sim_test01' },
    })
  })
})
