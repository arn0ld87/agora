/**
 * Graph-Leser (#1797, Etappe 2): Zod-Schemas fuer die Antworten, die die
 * Ansichten lesen, und das reine Ansichtsmodell (Entitaeten, Beziehungen,
 * Typen mit Zaehlern, Filter, Sortierung).
 *
 * `GET /api/graph/data/<graph_id>` und die Simulationsliste haben im Backend
 * ein DTO bzw. ein Pydantic-Modell, aber noch keinen Frontend-Spiegel unter
 * `contracts/`. Dieses Ticket legt keine API-Vertraege an: die Schemas hier
 * lesen nur die Felder, die der Leser braucht (`.passthrough()`), damit der
 * Canvas die Rohdaten unveraendert bekommt.
 */
import { z } from 'zod'

const TimestampSchema = z.union([z.string(), z.number()]).nullish()

/**
 * Herkunftsmerkmal (#1808, ADR-0022) in der Leseantwort. Optional: Altgraphen
 * und Antworten ohne Feld bleiben gueltig; `origin: null` heisst „extrahiert“.
 * Der Zeitpunkt ist hier locker gelesen (Text oder Zahl), die strenge Form
 * steht in `contracts/graphEditContract`.
 */
export const GraphProvenanceSchema = z
  .object({
    origin: z.enum(['manual', 'edited']).nullish(),
    changed_at: TimestampSchema,
    episode_count: z.number().int().nonnegative().nullish(),
  })
  .passthrough()
export type GraphProvenance = z.infer<typeof GraphProvenanceSchema>

export const GraphNodeSchema = z
  .object({
    uuid: z.string().min(1),
    name: z.string().nullish(),
    labels: z.array(z.string()).nullish(),
    entity_type: z.string().nullish(),
    provenance: GraphProvenanceSchema.nullish(),
    summary: z.string().nullish(),
    attributes: z.record(z.string(), z.unknown()).nullish(),
    created_at: TimestampSchema,
  })
  .passthrough()

export const GraphEdgeSchema = z
  .object({
    uuid: z.string().min(1),
    name: z.string().nullish(),
    fact: z.string().nullish(),
    source_node_uuid: z.string().min(1),
    target_node_uuid: z.string().min(1),
    source_node_name: z.string().nullish(),
    target_node_name: z.string().nullish(),
    episode_ids: z.array(z.unknown()).nullish(),
    provenance: GraphProvenanceSchema.nullish(),
    created_at: TimestampSchema,
  })
  .passthrough()

export const GraphDataSchema = z
  .object({
    graph_id: z.string().min(1),
    nodes: z.array(GraphNodeSchema),
    edges: z.array(GraphEdgeSchema),
  })
  .passthrough()
export type GraphData = z.infer<typeof GraphDataSchema>

/** Eine Simulation (Lauf) aus `GET /api/simulation/list` bzw. `GET /api/simulation/<id>`. */
export const SimulationRefSchema = z
  .object({
    simulation_id: z.string().min(1),
    project_id: z.string().min(1),
    status: z.string(),
    created_at: z.string().nullish(),
    updated_at: z.string().nullish(),
  })
  .passthrough()
export type SimulationRef = z.infer<typeof SimulationRefSchema>

export const SimulationRefListSchema = z.array(SimulationRefSchema)

// ---------------------------------------------------------------------------
// Ansichtsmodell
// ---------------------------------------------------------------------------

/** Formen je Typ: der Typ ist so nicht nur ueber Farbe erkennbar. */
const TYPE_GLYPHS = ['●', '■', '▲', '◆', '★', '⬟', '✚', '⬢'] as const

export interface ReaderEntity {
  id: string
  name: string
  type: string
  summary: string
  aliases: string[]
  createdAt: string | null
  /** Zahl der Beziehungen, an denen die Entitaet beteiligt ist. */
  degree: number
  raw: GraphData['nodes'][number]
}

export interface ReaderRelation {
  id: string
  label: string
  fact: string
  fromId: string
  fromName: string
  toId: string
  toName: string
  /** Zahl der Quellenfragmente (`episode_ids`), die die Beziehung belegen. */
  episodeCount: number
  createdAt: string | null
  raw: GraphData['edges'][number]
}

export interface ReaderType {
  name: string
  count: number
  glyph: string
}

export interface ReaderModel {
  graphId: string
  entities: ReaderEntity[]
  relations: ReaderRelation[]
  types: ReaderType[]
}

function stamp(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null
  return String(value)
}

function aliasesOf(attributes: Record<string, unknown> | null | undefined): string[] {
  const raw = attributes?.['aliases'] ?? attributes?.['alias'] ?? attributes?.['_agora_aliases']
  if (Array.isArray(raw)) return raw.filter((a): a is string => typeof a === 'string' && a.length > 0)
  if (typeof raw === 'string' && raw.length > 0) return [raw]
  return []
}

export function typeOfNode(
  labels?: readonly string[] | null,
  entityType?: string | null,
): string {
  if (entityType && entityType.trim()) return entityType.trim()
  return labels?.find((label) => label !== 'Entity') || 'Entity'
}

export function buildReaderModel(data: GraphData): ReaderModel {
  const names = new Map<string, string>()
  for (const node of data.nodes) names.set(node.uuid, node.name || node.uuid)

  const degree = new Map<string, number>()
  const relations: ReaderRelation[] = data.edges.map((edge) => {
    degree.set(edge.source_node_uuid, (degree.get(edge.source_node_uuid) ?? 0) + 1)
    if (edge.target_node_uuid !== edge.source_node_uuid) {
      degree.set(edge.target_node_uuid, (degree.get(edge.target_node_uuid) ?? 0) + 1)
    }
    return {
      id: edge.uuid,
      label: edge.name || '',
      fact: edge.fact || '',
      fromId: edge.source_node_uuid,
      fromName: names.get(edge.source_node_uuid) || edge.source_node_name || edge.source_node_uuid,
      toId: edge.target_node_uuid,
      toName: names.get(edge.target_node_uuid) || edge.target_node_name || edge.target_node_uuid,
      episodeCount: edge.episode_ids?.length ?? 0,
      createdAt: stamp(edge.created_at),
      raw: edge,
    }
  })

  const entities: ReaderEntity[] = data.nodes.map((node) => ({
    id: node.uuid,
    name: node.name || node.uuid,
    type: typeOfNode(node.labels, (node as { entity_type?: string | null }).entity_type),
    summary: node.summary || '',
    aliases: aliasesOf(node.attributes),
    createdAt: stamp(node.created_at),
    degree: degree.get(node.uuid) ?? 0,
    raw: node,
  }))

  const counts = new Map<string, number>()
  for (const entity of entities) counts.set(entity.type, (counts.get(entity.type) ?? 0) + 1)
  const types: ReaderType[] = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'de'))
    .map(([name, count], index) => ({ name, count, glyph: TYPE_GLYPHS[index % TYPE_GLYPHS.length] }))

  return { graphId: data.graph_id, entities, relations, types }
}

export interface EntityFilter {
  query: string
  /** Leer = alle Typen. */
  types: ReadonlySet<string>
}

export function filterEntities(entities: readonly ReaderEntity[], filter: EntityFilter): ReaderEntity[] {
  const q = filter.query.trim().toLocaleLowerCase('de')
  return entities.filter((entity) => {
    if (filter.types.size > 0 && !filter.types.has(entity.type)) return false
    if (!q) return true
    return (
      entity.name.toLocaleLowerCase('de').includes(q) ||
      entity.aliases.some((alias) => alias.toLocaleLowerCase('de').includes(q))
    )
  })
}

export function filterRelations(
  relations: readonly ReaderRelation[],
  entityIds: ReadonlySet<string>,
  query: string,
): ReaderRelation[] {
  const q = query.trim().toLocaleLowerCase('de')
  return relations.filter((relation) => {
    if (!entityIds.has(relation.fromId) && !entityIds.has(relation.toId)) return false
    if (!q) return true
    return (
      relation.label.toLocaleLowerCase('de').includes(q) ||
      relation.fromName.toLocaleLowerCase('de').includes(q) ||
      relation.toName.toLocaleLowerCase('de').includes(q)
    )
  })
}

export type SortDirection = 'asc' | 'desc'

/** Stabile Sortierung nach einem Schluessel; Zahlen numerisch, Text nach de-Kollation. */
export function sortRows<T>(
  rows: readonly T[],
  key: (row: T) => string | number,
  direction: SortDirection,
): T[] {
  const sign = direction === 'asc' ? 1 : -1
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const ka = key(a.row)
      const kb = key(b.row)
      const cmp =
        typeof ka === 'number' && typeof kb === 'number'
          ? ka - kb
          : String(ka).localeCompare(String(kb), 'de', { sensitivity: 'base' })
      return cmp !== 0 ? sign * cmp : a.index - b.index
    })
    .map(({ row }) => row)
}
