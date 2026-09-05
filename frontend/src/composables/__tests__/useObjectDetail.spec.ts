import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import type { ShelfObject } from '../../types/shelf'

vi.mock('../../api/report', () => ({ getReport: vi.fn(), getReportEvidence: vi.fn() }))
vi.mock('../../api/graph', () => ({ getGraphData: vi.fn() }))
vi.mock('../../api/simulation', () => ({ listPersonaTemplates: vi.fn() }))

import { getReport, getReportEvidence } from '../../api/report'
import { getGraphData } from '../../api/graph'
import { listPersonaTemplates } from '../../api/simulation'
import { useObjectDetail } from '../useObjectDetail'

// t-Stub: gibt den Schluessel zurueck (+ JSON der Values), Assertions laufen ueber Schluessel.
const t = (key: string, values?: Record<string, unknown>): string => (values ? `${key}:${JSON.stringify(values)}` : key)

function makeObject(over: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'bericht',
    id: 'report_1',
    title: 'Ein Bericht',
    statusLine: 'fertig',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'report_1',
    nextAction: null,
    active: null,
    ...over,
  }
}

/** Leere Evidence-Map — Default fuer Tests, die die Confidence-Verteilung nicht pruefen. */
const EMPTY_EVIDENCE_MAP = { schema_version: 3, report_id: 'report_1', simulation_id: 'sim_1', evidence_index: {}, global_evidence_refs: [], sections: [] }

describe('useObjectDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getReportEvidence).mockResolvedValue({ success: true, data: EMPTY_EVIDENCE_MAP } as never)
  })

  it('laedt fuer einen Bericht die Gliederung als Bestandteile', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: {
        outline: {
          title: 'Titel',
          summary: 'Kurzfassung des Berichts',
          sections: [{ title: 'Lage', description: 'Beschreibung A' }],
        },
      },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject())
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(detail.value?.summary).toBe('Kurzfassung des Berichts')
    expect(detail.value?.parts).toEqual([{ title: 'Lage', description: 'Beschreibung A' }])
  })

  it('laedt fuer einen Graphen die Kennzahlen', async () => {
    vi.mocked(getGraphData).mockResolvedValue({
      success: true,
      data: { nodes: [{}, {}, {}], edges: [{}] },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject({ kind: 'graph', id: 'proj_1', graphId: 'graph_1' }))
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(getGraphData).toHaveBeenCalledWith('graph_1')
    expect(detail.value?.parts).toEqual([
      { title: 'shelf.dossier.graphEntities', description: '3' },
      { title: 'shelf.dossier.graphRelations', description: '1' },
    ])
  })

  it('zeigt fuer einen Personasatz Beruf, Land, Interessen und Kurzbeschreibung', async () => {
    vi.mocked(listPersonaTemplates).mockResolvedValue({
      success: true,
      data: {
        count: 2,
        templates: [
          { template_id: 'other', name: 'Falsch' },
          {
            template_id: 'tpl_1',
            name: 'Sachbearbeiterin',
            persona: 'Skeptisch gegenüber Reformen.',
            profession: 'Verwaltung',
            country: 'DE',
            interested_topics: ['Rente', 'Wohnen'],
            bio: 'Seit 12 Jahren im Amt.',
          },
        ],
      },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject({ kind: 'personasatz', id: 'tpl_1' }))
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(detail.value?.summary).toBe('Skeptisch gegenüber Reformen.')
    expect(detail.value?.parts).toEqual([
      { title: 'shelf.dossier.personaProfession', description: 'Verwaltung' },
      { title: 'shelf.dossier.personaCountry', description: 'DE' },
      { title: 'shelf.dossier.personaTopics', description: 'Rente, Wohnen' },
      { title: 'shelf.dossier.personaBio', description: 'Seit 12 Jahren im Amt.' },
    ])
  })

  it('laesst leere Felder eines Personasatzes weg, statt sie leer anzuzeigen', async () => {
    vi.mocked(listPersonaTemplates).mockResolvedValue({
      success: true,
      data: { count: 1, templates: [{ template_id: 'tpl_2', name: 'Knapp', profession: 'Pflege' }] },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject({ kind: 'personasatz', id: 'tpl_2' }))
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(detail.value?.parts).toEqual([
      { title: 'shelf.dossier.personaProfession', description: 'Pflege' },
    ])
    expect(detail.value?.summary).toBe('')
  })

  it('laedt nichts fuer einen Lauf ohne Personas und ohne verknuepften Bericht', async () => {
    const obj = ref<ShelfObject | null>(makeObject({ kind: 'lauf', id: 'sim_1', jobs: [] }))
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve()

    expect(getReport).not.toHaveBeenCalled()
    expect(getGraphData).not.toHaveBeenCalled()
    expect(listPersonaTemplates).not.toHaveBeenCalled()
    expect(detail.value).toBeNull()
  })

  it('Lauf mit Personas und verknuepftem Bericht bekommt Bestandteile Akteure + Ausgabe mit Zahl + Link', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: { evidence_sections: 5 },
    } as never)

    const obj = ref<ShelfObject | null>(
      makeObject({
        kind: 'lauf',
        id: 'sim_1',
        personaCount: 12,
        jobs: [
          {
            runId: 'run_2',
            runType: 'simulation_run',
            status: 'completed',
            message: '',
            updatedAt: '2026-08-18T11:00:00Z',
            linkedIds: { simulation_id: 'sim_1', report_id: 'report_9' },
          },
        ],
      }),
    )
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(getReport).toHaveBeenCalledWith('report_9')
    expect(detail.value?.parts).toEqual([
      {
        title: 'views.dossier.parts.actors',
        description: 'views.dossier.parts.actorsDesc:{"n":12}',
        count: 12,
        to: { name: 'StepEnvSetup', params: { projectId: 'sim_1' } },
      },
      {
        title: 'views.dossier.parts.output',
        description: 'views.dossier.parts.outputDesc:{"n":5}',
        count: 5,
        to: { name: 'StepReport', params: { reportId: 'report_9' } },
      },
    ])
  })

  it('Bericht bekommt Confidence-Verteilung, Aussagen- und Luecken-Zahl aus der Evidence-Map', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: { outline: { title: 'T', summary: 'S', sections: [] }, evidence_sections: 3, red_team_findings: ['Befund A'] },
    } as never)
    vi.mocked(getReportEvidence).mockResolvedValue({
      success: true,
      data: {
        ...EMPTY_EVIDENCE_MAP,
        sections: [
          {
            section_index: 1,
            section_title: 'Lage',
            section_summary: 'x',
            claims: [
              { claim_id: 'claim_01', confidence_label: 'high' },
              { claim_id: 'claim_02', confidence_label: 'high' },
              { claim_id: 'claim_03', confidence_label: 'low' },
            ],
            hypotheses: [],
            hypotheses_appendix: [],
            data_gaps: [{ gap_id: 'gap_01' }],
            structured_metadata: {},
            generation_failed: false,
            unbound_evidence_refs: [],
            unverified_statements: [],
          },
        ],
      },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject({ id: 'report_9' }))
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()

    expect(detail.value?.confidenceDistribution).toEqual({ high: 2, low: 1 })
    expect(detail.value?.claimsCount).toBe(3)
    expect(detail.value?.gapsCount).toBe(1)
    expect(detail.value?.evidenceSections).toBe(3)
    expect(detail.value?.redTeamFindings).toEqual(['Befund A'])
  })

  it('haelt einen fehlgeschlagenen Abruf von der Ablage fern', async () => {
    vi.mocked(getReport).mockRejectedValue(new Error('kaputt'))

    const obj = ref<ShelfObject | null>(makeObject())
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(detail.value).toBeNull()
  })

  it('verwirft die Details beim Abwaehlen', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: { outline: { title: 'T', summary: 'S', sections: [{ title: 'A', description: 'B' }] } },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject())
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(detail.value).not.toBeNull()

    obj.value = null
    await nextTick(); await Promise.resolve()
    expect(detail.value).toBeNull()
  })
})
