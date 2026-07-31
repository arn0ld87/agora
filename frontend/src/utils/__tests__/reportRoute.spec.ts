import { describe, it, expect } from 'vitest'

import { buildReportRoute } from '../reportRoute'

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
