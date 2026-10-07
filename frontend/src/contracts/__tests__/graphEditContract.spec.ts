/**
 * Zod-Spiegel-Tests für den Graph-Bearbeitungs-Vertrag (#1808, Etappe 8).
 *
 * Backend-Quelle: backend/app/contracts/graph_edit_contract.py
 * Schemas: schemas/graph-*.schema.json
 */
import { describe, it, expect } from 'vitest'
import {
  EntityCreateSchema,
  EntityDeleteResultSchema,
  EntityMergeResultSchema,
  EntityMergeSchema,
  EntityUpdateSchema,
  GraphDuplicateJobSchema,
  GraphDuplicateRequestSchema,
  GraphEdgeViewSchema,
  GraphLockStateSchema,
  GraphLockUserSchema,
  GraphNodeViewSchema,
  GraphProvenanceInfoSchema,
  RelationCreateSchema,
  RelationDeleteResultSchema,
  RelationUpdateSchema,
} from '../graphEditContract'
import entityCreateJson from '../../../../schemas/graph-entity-create.schema.json'
import entityUpdateJson from '../../../../schemas/graph-entity-update.schema.json'
import entityMergeJson from '../../../../schemas/graph-entity-merge.schema.json'
import entityMergeResultJson from '../../../../schemas/graph-entity-merge-result.schema.json'
import entityDeleteResultJson from '../../../../schemas/graph-entity-delete-result.schema.json'
import relationCreateJson from '../../../../schemas/graph-relation-create.schema.json'
import relationUpdateJson from '../../../../schemas/graph-relation-update.schema.json'
import relationDeleteResultJson from '../../../../schemas/graph-relation-delete-result.schema.json'
import nodeViewJson from '../../../../schemas/graph-node-view.schema.json'
import edgeViewJson from '../../../../schemas/graph-edge-view.schema.json'
import provenanceJson from '../../../../schemas/graph-provenance-info.schema.json'
import lockStateJson from '../../../../schemas/graph-lock-state.schema.json'
import lockUserJson from '../../../../schemas/graph-lock-user.schema.json'
import duplicateRequestJson from '../../../../schemas/graph-duplicate-request.schema.json'
import duplicateJobJson from '../../../../schemas/graph-duplicate-job.schema.json'

const UUID_A = '11111111-1111-4111-8111-111111111111'
const UUID_B = '22222222-2222-4222-8222-222222222222'

function propertyKeys(schema: { properties?: Record<string, unknown> }) {
  return Object.keys(schema.properties ?? {}).sort()
}
function shapeKeys(schema: { shape: Record<string, unknown> }) {
  return Object.keys(schema.shape).sort()
}

describe('graphEditContract — Schema-Drift', () => {
  const pairs: Array<[string, { shape: Record<string, unknown> }, { properties?: Record<string, unknown> }]> = [
    ['EntityCreate', EntityCreateSchema, entityCreateJson],
    ['EntityUpdate', EntityUpdateSchema, entityUpdateJson],
    ['EntityMerge', EntityMergeSchema, entityMergeJson],
    ['EntityMergeResult', EntityMergeResultSchema, entityMergeResultJson],
    ['EntityDeleteResult', EntityDeleteResultSchema, entityDeleteResultJson],
    ['RelationCreate', RelationCreateSchema, relationCreateJson],
    ['RelationUpdate', RelationUpdateSchema, relationUpdateJson],
    ['RelationDeleteResult', RelationDeleteResultSchema, relationDeleteResultJson],
    ['GraphNodeView', GraphNodeViewSchema, nodeViewJson],
    ['GraphEdgeView', GraphEdgeViewSchema, edgeViewJson],
    ['GraphProvenanceInfo', GraphProvenanceInfoSchema, provenanceJson],
    ['GraphLockState', GraphLockStateSchema, lockStateJson],
    ['GraphLockUser', GraphLockUserSchema, lockUserJson],
    ['GraphDuplicateRequest', GraphDuplicateRequestSchema, duplicateRequestJson],
    ['GraphDuplicateJob', GraphDuplicateJobSchema, duplicateJobJson],
  ]
  it.each(pairs)('%s hat dieselben Felder wie das JSON-Schema', (_name, zodSchema, json) => {
    expect(shapeKeys(zodSchema)).toEqual(propertyKeys(json))
  })
})

describe('graphEditContract — Eingaben', () => {
  it('EntityCreate kürzt Leerraum und entfernt doppelte Aliase', () => {
    const out = EntityCreateSchema.parse({
      client_request_id: UUID_A,
      name: '  Stadtrat ',
      entity_type: 'Organisation',
      aliases: ['Rat', 'rat', ' Gemeinderat '],
    })
    expect(out.name).toBe('Stadtrat')
    expect(out.summary).toBe('')
    expect(out.aliases).toEqual(['Rat', 'Gemeinderat'])
  })

  it('EntityCreate lehnt leeren Namen, fremde Felder und falsche UUID ab', () => {
    const base = { client_request_id: UUID_A, name: 'X', entity_type: 'T' }
    expect(EntityCreateSchema.safeParse({ ...base, name: '   ' }).success).toBe(false)
    expect(EntityCreateSchema.safeParse({ ...base, extra: 1 }).success).toBe(false)
    expect(EntityCreateSchema.safeParse({ ...base, client_request_id: 'abc' }).success).toBe(false)
  })

  it('EntityUpdate verlangt mindestens ein Feld und kein null', () => {
    expect(EntityUpdateSchema.safeParse({}).success).toBe(false)
    expect(EntityUpdateSchema.safeParse({ name: null }).success).toBe(false)
    expect(EntityUpdateSchema.safeParse({ summary: '' }).success).toBe(true)
  })

  it('EntityMerge: Quellen verschieden vom Ziel und untereinander', () => {
    expect(EntityMergeSchema.safeParse({ target_uuid: UUID_A, source_uuids: [UUID_B] }).success).toBe(true)
    expect(EntityMergeSchema.safeParse({ target_uuid: UUID_A, source_uuids: [UUID_A] }).success).toBe(false)
    expect(EntityMergeSchema.safeParse({ target_uuid: UUID_A, source_uuids: [UUID_B, UUID_B] }).success).toBe(false)
    expect(EntityMergeSchema.safeParse({ target_uuid: UUID_A, source_uuids: [] }).success).toBe(false)
  })

  it('RelationCreate lehnt Selbstbezug ab, RelationUpdate verlangt ein Feld', () => {
    const rel = { client_request_id: UUID_A, source_uuid: UUID_A, target_uuid: UUID_B, name: 'LEITET', fact: 'A leitet B' }
    expect(RelationCreateSchema.safeParse(rel).success).toBe(true)
    expect(RelationCreateSchema.safeParse({ ...rel, target_uuid: UUID_A }).success).toBe(false)
    expect(RelationUpdateSchema.safeParse({}).success).toBe(false)
    expect(RelationUpdateSchema.safeParse({ fact: 'neu' }).success).toBe(true)
  })

  it('GraphDuplicateRequest verlangt Name und client_request_id', () => {
    expect(GraphDuplicateRequestSchema.safeParse({ client_request_id: UUID_A, name: 'Kopie' }).success).toBe(true)
    expect(GraphDuplicateRequestSchema.safeParse({ name: 'Kopie' }).success).toBe(false)
  })
})

describe('graphEditContract — Antworten', () => {
  it('GraphNodeView ohne Herkunft bedeutet "extrahiert" (origin null)', () => {
    const node = GraphNodeViewSchema.parse({ uuid: UUID_A, name: 'A' })
    expect(node.provenance).toEqual({ origin: null, changed_at: null, episode_count: 0 })
    expect(node.labels).toEqual([])
  })

  it('GraphProvenanceInfo nimmt nur manual, edited oder null an', () => {
    expect(GraphProvenanceInfoSchema.safeParse({ origin: 'manual', changed_at: '2026-10-07T10:00:00Z' }).success).toBe(true)
    expect(GraphProvenanceInfoSchema.safeParse({ origin: 'extracted' }).success).toBe(false)
  })

  it('GraphEdgeView, Ergebnisse und Sperrzustand', () => {
    expect(
      GraphEdgeViewSchema.safeParse({
        uuid: UUID_A, name: 'N', source_node_uuid: UUID_A, target_node_uuid: UUID_B,
        provenance: { origin: 'edited', changed_at: '2026-10-07T10:00:00Z', episode_count: 2 },
      }).success,
    ).toBe(true)
    expect(EntityDeleteResultSchema.parse({ uuid: UUID_A }).removed_relation_count).toBe(0)
    expect(EntityMergeResultSchema.parse({ target: { uuid: UUID_A, name: 'A' } }).merged_source_uuids).toEqual([])
    const lock = GraphLockStateSchema.parse({
      graph_id: 'g1', locked: true, used_by: [{ simulation_id: 'sim_1' }],
    })
    expect(lock.used_by[0]).toEqual({ simulation_id: 'sim_1', status: '', project_id: '', branch_name: null })
  })

  it('GraphDuplicateJob prüft Status und Fortschritt', () => {
    const job = { run_id: 'r', source_graph_id: 'a', graph_id: 'b', project_id: 'p', status: 'pending' }
    expect(GraphDuplicateJobSchema.safeParse(job).success).toBe(true)
    expect(GraphDuplicateJobSchema.safeParse({ ...job, status: 'weird' }).success).toBe(false)
    expect(GraphDuplicateJobSchema.safeParse({ ...job, progress: 101 }).success).toBe(false)
  })
})
