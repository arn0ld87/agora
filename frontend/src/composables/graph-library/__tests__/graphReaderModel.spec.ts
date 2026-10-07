import { describe, expect, it } from 'vitest'
import { GraphDataSchema, buildReaderModel } from '../graphReaderModel'

const base = {
  graph_id: 'g1',
  nodes: [{ uuid: 'n1', name: 'A', labels: ['Organisation'] }],
  edges: [{ uuid: 'e1', source_node_uuid: 'n1', target_node_uuid: 'n1', name: 'X', fact: 'f' }],
}

describe('GraphDataSchema — Herkunft (#1808)', () => {
  it('Altgraphen ohne provenance und entity_type bleiben gültig', () => {
    const parsed = GraphDataSchema.parse(base)
    expect(parsed.nodes[0].provenance).toBeUndefined()
    expect(parsed.edges[0].provenance).toBeUndefined()
    expect(buildReaderModel(parsed).entities).toHaveLength(1)
  })

  it('reicht provenance und entity_type an Knoten und Kanten typisiert durch', () => {
    const parsed = GraphDataSchema.parse({
      ...base,
      nodes: [
        {
          ...base.nodes[0],
          entity_type: 'Organisation',
          provenance: { origin: 'manual', changed_at: '2026-10-07T10:00:00Z', episode_count: 0 },
        },
      ],
      edges: [
        { ...base.edges[0], provenance: { origin: 'edited', changed_at: '2026-10-07T11:00:00Z', episode_count: 2 } },
      ],
    })
    expect(parsed.nodes[0].entity_type).toBe('Organisation')
    expect(parsed.nodes[0].provenance?.origin).toBe('manual')
    expect(parsed.edges[0].provenance?.origin).toBe('edited')
    expect(parsed.edges[0].provenance?.episode_count).toBe(2)
    const model = buildReaderModel(parsed)
    expect(model.entities[0].raw.provenance?.origin).toBe('manual')
  })

  it('akzeptiert die Leseantwort des Backends für extrahierte Elemente (origin null)', () => {
    const parsed = GraphDataSchema.parse({
      ...base,
      nodes: [
        { ...base.nodes[0], entity_type: null, provenance: { origin: null, changed_at: null, episode_count: 0 } },
      ],
    })
    expect(parsed.nodes[0].provenance?.origin).toBeNull()
  })
})
