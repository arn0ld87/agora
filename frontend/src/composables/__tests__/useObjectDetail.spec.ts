import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import type { ShelfObject } from '../../types/shelf'

vi.mock('../../api/report', () => ({ getReport: vi.fn() }))
vi.mock('../../api/graph', () => ({ getGraphData: vi.fn() }))

import { getReport } from '../../api/report'
import { getGraphData } from '../../api/graph'
import { useObjectDetail } from '../useObjectDetail'

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
    const { detail } = useObjectDetail(obj)
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
    const { detail } = useObjectDetail(obj)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(getGraphData).toHaveBeenCalledWith('graph_1')
    expect(detail.value?.parts.map((p) => p.description)).toEqual(['3', '1'])
  })

  it('laedt nichts fuer Sorten ohne Detail-Endpunkt', async () => {
    const obj = ref<ShelfObject | null>(makeObject({ kind: 'lauf', id: 'sim_1' }))
    const { detail } = useObjectDetail(obj)
    await nextTick(); await Promise.resolve()

    expect(getReport).not.toHaveBeenCalled()
    expect(getGraphData).not.toHaveBeenCalled()
    expect(detail.value).toBeNull()
  })

  it('haelt einen fehlgeschlagenen Abruf von der Ablage fern', async () => {
    vi.mocked(getReport).mockRejectedValue(new Error('kaputt'))

    const obj = ref<ShelfObject | null>(makeObject())
    const { detail } = useObjectDetail(obj)
    await nextTick(); await Promise.resolve(); await Promise.resolve()

    expect(detail.value).toBeNull()
  })

  it('verwirft die Details beim Abwaehlen', async () => {
    vi.mocked(getReport).mockResolvedValue({
      success: true,
      data: { outline: { title: 'T', summary: 'S', sections: [{ title: 'A', description: 'B' }] } },
    } as never)

    const obj = ref<ShelfObject | null>(makeObject())
    const { detail } = useObjectDetail(obj)
    await nextTick(); await Promise.resolve(); await Promise.resolve()
    expect(detail.value).not.toBeNull()

    obj.value = null
    await nextTick(); await Promise.resolve()
    expect(detail.value).toBeNull()
  })
})
