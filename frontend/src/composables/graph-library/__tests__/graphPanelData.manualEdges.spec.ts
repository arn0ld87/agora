import { describe, expect, it } from 'vitest'
import { buildGraphRenderData, manualEdgeDashPattern } from '../../../components/graph/graphPanelData'

const node = (uuid: string, name: string) => ({
  uuid,
  name,
  labels: ['Organisation'],
  attributes: {},
  created_at: null,
})

const edge = (uuid: string, from: string, to: string, origin: string | null) => ({
  uuid,
  name: 'KENNT',
  fact: 'kennt',
  source_node_uuid: from,
  target_node_uuid: to,
  episode_ids: [],
  created_at: null,
  provenance: { origin },
})

describe('buildGraphRenderData: gestrichelte Handkanten', () => {
  const graph = {
    nodes: [node('n1', 'A'), node('n2', 'B'), node('n3', 'C')],
    edges: [
      edge('e1', 'n1', 'n2', null),
      edge('e2', 'n1', 'n3', 'manual'),
      edge('e3', 'n2', 'n3', 'edited'),
    ],
  }

  it('markiert von Hand angelegte und geaenderte Kanten als handgemacht', () => {
    const { edges } = buildGraphRenderData(graph)
    const byUuid = new Map(edges.map((e) => [e.rawData['uuid'] as string, e]))
    expect(byUuid.get('e1')?.isHandMade).toBe(false)
    expect(byUuid.get('e2')?.isHandMade).toBe(true)
    expect(byUuid.get('e3')?.isHandMade).toBe(true)
  })

  it('gibt Handkanten ein Strichmuster und extrahierten keines', () => {
    const { edges } = buildGraphRenderData(graph)
    const byUuid = new Map(edges.map((e) => [e.rawData['uuid'] as string, e]))
    expect(manualEdgeDashPattern(byUuid.get('e1')!)).toBeNull()
    expect(manualEdgeDashPattern(byUuid.get('e2')!)).toBeTruthy()
    expect(manualEdgeDashPattern(byUuid.get('e3')!)).toBeTruthy()
  })

  it('behandelt einen Graphen ohne Merkmal als vollstaendig extrahiert', () => {
    const { edges } = buildGraphRenderData({
      nodes: [node('n1', 'A'), node('n2', 'B')],
      edges: [{ uuid: 'e1', name: 'KENNT', source_node_uuid: 'n1', target_node_uuid: 'n2' }],
    })
    expect(edges[0]?.isHandMade).toBe(false)
  })
})