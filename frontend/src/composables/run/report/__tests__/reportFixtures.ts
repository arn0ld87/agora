/** Gemeinsame Testdaten der Bericht-Reiter-Specs (Etappe 5, #1804). */
import { EvidenceMapSchema, ReportSchema, type Report } from '@/contracts/reportContract'

export function reportData(over: Record<string, unknown> = {}): Report {
  return ReportSchema.parse({
    schema_version: 2,
    report_id: 'report_1',
    simulation_id: 'sim_1',
    graph_id: 'g1',
    simulation_requirement: 'Wie reagiert die Branche auf die Abgabe?',
    status: 'completed',
    created_at: '2026-10-05T10:00:00Z',
    completed_at: '2026-10-05T10:30:00Z',
    markdown_content: '# Bericht\n\nGanzer Text.',
    outline: {
      title: 'Branche und Abgabe',
      summary: 'Zusammenfassung des Berichts.',
      sections: [
        { title: 'Risiken', description: 'Risiken der Abgabe' },
        { title: 'Akteure', description: 'Wer reagiert' },
      ],
    },
    ...over,
  })
}

export function evidenceMap(report = 'report_1') {
  return EvidenceMapSchema.parse({
    schema_version: 3,
    report_id: report,
    simulation_id: 'sim_1',
    evidence_index: {},
    sections: [],
  })
}

/** Rohform der Listenantwort (`GET /api/report/list`). */
export function listEnvelope(items: unknown[]) {
  return { success: true, data: items }
}
