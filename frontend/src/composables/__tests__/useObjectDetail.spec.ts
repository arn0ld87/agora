import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import type { ShelfObject } from '../../types/shelf'

vi.mock('../../api/report', () => ({ getReport: vi.fn() }))
vi.mock('../../api/graph', () => ({ getGraphData: vi.fn() }))
vi.mock('../../api/simulation', () => ({ listPersonaTemplates: vi.fn() }))

import { getReport } from '../../api/report'
import { getGraphData } from '../../api/graph'
import { listPersonaTemplates } from '../../api/simulation'
import { useObjectDetail } from '../useObjectDetail'

// t-Stub: gibt den Schluessel zurueck, Assertions laufen ueber Schluessel.
const t = (key: string): string => key

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

describe('useObjectDetail', () => {
  beforeEach(() => vi.clearAllMocks())

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

  it('laedt nichts fuer Sorten ohne Detail-Endpunkt', async () => {
    const obj = ref<ShelfObject | null>(makeObject({ kind: 'lauf', id: 'sim_1' }))
    const { detail } = useObjectDetail(obj, t)
    await nextTick(); await Promise.resolve()

    expect(getReport).not.toHaveBeenCalled()
    expect(getGraphData).not.toHaveBeenCalled()
    expect(listPersonaTemplates).not.toHaveBeenCalled()
    expect(detail.value).toBeNull()
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
