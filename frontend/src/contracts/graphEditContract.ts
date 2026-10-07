/**
 * Graph-Bearbeitungs-Vertrag — Zod-Spiegel (#1808, Etappe 8, ADR-0022).
 *
 * Hand-gepflegt, 1:1 zu `schemas/graph-*.schema.json`. Änderungen am
 * Pydantic-Modell (`backend/app/contracts/graph_edit_contract.py`) →
 * Schema-Dump → diese Datei synchronisieren; `graphEditContract.spec.ts`
 * vergleicht die Feldlisten.
 *
 * Herkunft: `origin: null` heißt „extrahiert“ (Bestand, kein Merkmal);
 * `manual` = von Hand angelegt, `edited` = extrahiert, danach von Hand
 * geändert.
 */
import { z } from 'zod'

export const MAX_ALIASES = 20
export const MAX_MERGE_SOURCES = 50

const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/

const ElementUuid = z.string().regex(UUID_PATTERN)
const EntityName = z.string().trim().min(1).max(200)
const EntityTypeName = z.string().trim().min(1).max(100)
const RelationName = z.string().trim().min(1).max(100)
const EntitySummary = z.string().trim().max(2000)
const RelationFact = z.string().trim().min(1).max(2000)
const AliasName = z.string().trim().min(1).max(200)

/** Ein Zeitpunkt aus dem Backend (ISO-Text, `datetime` im Pydantic-Vertrag). */
const Timestamp = z.string().nullable().default(null)

function dedupeAliases(values: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const value of values) {
    const key = value.toLowerCase()
    if (!seen.has(key)) {
      seen.add(key)
      out.push(value)
    }
  }
  return out
}

/** Mindestens ein Feld; ein gesetztes Feld darf nicht `undefined` sein (null scheitert am Typ). */
function atLeastOneField(value: Record<string, unknown>, ctx: z.RefinementCtx): void {
  if (Object.values(value).every((v) => v === undefined)) {
    ctx.addIssue({ code: 'custom', message: 'mindestens ein Feld muss angegeben werden' })
  }
}

// === Herkunft und Ansichten ===

export const GraphOriginSchema = z.enum(['manual', 'edited'])
export type GraphOrigin = z.infer<typeof GraphOriginSchema>

export const GraphProvenanceInfoSchema = z
  .object({
    origin: GraphOriginSchema.nullable().default(null),
    changed_at: Timestamp,
    episode_count: z.number().int().min(0).default(0),
  })
  .strict()
export type GraphProvenanceInfo = z.infer<typeof GraphProvenanceInfoSchema>

export const GraphNodeViewSchema = z
  .object({
    uuid: z.string().min(1),
    name: z.string(),
    labels: z.array(z.string()).default(() => []),
    entity_type: z.string().nullable().default(null),
    summary: z.string().default(''),
    attributes: z.record(z.string(), z.unknown()).default(() => ({})),
    created_at: Timestamp,
    provenance: GraphProvenanceInfoSchema.default(() => GraphProvenanceInfoSchema.parse({})),
  })
  .strict()
export type GraphNodeView = z.infer<typeof GraphNodeViewSchema>

export const GraphEdgeViewSchema = z
  .object({
    uuid: z.string().min(1),
    name: z.string(),
    fact: z.string().default(''),
    source_node_uuid: z.string().min(1),
    target_node_uuid: z.string().min(1),
    attributes: z.record(z.string(), z.unknown()).default(() => ({})),
    created_at: Timestamp,
    valid_at: Timestamp,
    invalid_at: Timestamp,
    expired_at: Timestamp,
    valid_from_round: z.number().int().nullable().default(null),
    valid_to_round: z.number().int().nullable().default(null),
    reinforced_count: z.number().int().default(1),
    episode_ids: z.array(z.string()).default(() => []),
    provenance: GraphProvenanceInfoSchema.default(() => GraphProvenanceInfoSchema.parse({})),
  })
  .strict()
export type GraphEdgeView = z.infer<typeof GraphEdgeViewSchema>

// === Anfragen ===

export const EntityCreateSchema = z
  .object({
    client_request_id: z.string().regex(UUID_PATTERN),
    name: EntityName,
    entity_type: EntityTypeName,
    summary: EntitySummary.default(''),
    aliases: z.array(AliasName).max(MAX_ALIASES).default(() => []).transform(dedupeAliases),
  })
  .strict()
export type EntityCreate = z.infer<typeof EntityCreateSchema>
export type EntityCreateInput = z.input<typeof EntityCreateSchema>

export const EntityUpdateSchema = z
  .object({
    name: EntityName.optional(),
    entity_type: EntityTypeName.optional(),
    summary: EntitySummary.optional(),
    aliases: z.array(AliasName).max(MAX_ALIASES).transform(dedupeAliases).optional(),
  })
  .strict()
  .superRefine(atLeastOneField)
export type EntityUpdate = z.infer<typeof EntityUpdateSchema>
export type EntityUpdateInput = z.input<typeof EntityUpdateSchema>

export const EntityMergeSchema = z
  .object({
    target_uuid: ElementUuid,
    source_uuids: z.array(ElementUuid).min(1).max(MAX_MERGE_SOURCES),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.source_uuids.includes(value.target_uuid)) {
      ctx.addIssue({ code: 'custom', message: 'target_uuid darf nicht in source_uuids vorkommen' })
    }
    if (new Set(value.source_uuids).size !== value.source_uuids.length) {
      ctx.addIssue({ code: 'custom', message: 'source_uuids dürfen sich nicht wiederholen' })
    }
  })
export type EntityMerge = z.infer<typeof EntityMergeSchema>

export const RelationCreateSchema = z
  .object({
    client_request_id: z.string().regex(UUID_PATTERN),
    source_uuid: ElementUuid,
    target_uuid: ElementUuid,
    name: RelationName,
    fact: RelationFact,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.source_uuid === value.target_uuid) {
      ctx.addIssue({ code: 'custom', message: 'Quelle und Ziel dürfen nicht dieselbe Entität sein' })
    }
  })
export type RelationCreate = z.infer<typeof RelationCreateSchema>
export type RelationCreateInput = z.input<typeof RelationCreateSchema>

export const RelationUpdateSchema = z
  .object({
    name: RelationName.optional(),
    fact: RelationFact.optional(),
  })
  .strict()
  .superRefine(atLeastOneField)
export type RelationUpdate = z.infer<typeof RelationUpdateSchema>
export type RelationUpdateInput = z.input<typeof RelationUpdateSchema>

// === Ergebnisse ===

export const EntityMergeResultSchema = z
  .object({
    target: GraphNodeViewSchema,
    merged_source_uuids: z.array(z.string()).default(() => []),
    rewired_relation_count: z.number().int().min(0).default(0),
    dropped_relation_count: z.number().int().min(0).default(0),
  })
  .strict()
export type EntityMergeResult = z.infer<typeof EntityMergeResultSchema>

export const EntityDeleteResultSchema = z
  .object({
    uuid: z.string().min(1),
    removed_relation_count: z.number().int().min(0).default(0),
  })
  .strict()
export type EntityDeleteResult = z.infer<typeof EntityDeleteResultSchema>

export const RelationDeleteResultSchema = z.object({ uuid: z.string().min(1) }).strict()
export type RelationDeleteResult = z.infer<typeof RelationDeleteResultSchema>

// === Sperre ===

export const GraphLockUserSchema = z
  .object({
    simulation_id: z.string().min(1),
    status: z.string().default(''),
    project_id: z.string().default(''),
    branch_name: z.string().nullable().default(null),
  })
  .strict()
export type GraphLockUser = z.infer<typeof GraphLockUserSchema>

export const GraphLockStateSchema = z
  .object({
    graph_id: z.string(),
    locked: z.boolean(),
    used_by: z.array(GraphLockUserSchema).default(() => []),
  })
  .strict()
export type GraphLockState = z.infer<typeof GraphLockStateSchema>

// === Duplizieren ===

export const GraphDuplicateStatusSchema = z.enum([
  'pending',
  'processing',
  'completed',
  'failed',
  'stopped',
  'paused',
])
export type GraphDuplicateStatus = z.infer<typeof GraphDuplicateStatusSchema>

export const GraphDuplicateRequestSchema = z
  .object({
    client_request_id: z.string().regex(UUID_PATTERN),
    name: EntityName,
  })
  .strict()
export type GraphDuplicateRequest = z.infer<typeof GraphDuplicateRequestSchema>

export const GraphDuplicateJobSchema = z
  .object({
    run_id: z.string().min(1),
    source_graph_id: z.string().min(1),
    graph_id: z.string().min(1),
    project_id: z.string().min(1),
    status: GraphDuplicateStatusSchema,
    progress: z.number().int().min(0).max(100).default(0),
    message: z.string().default(''),
    error: z.string().nullable().default(null),
  })
  .strict()
export type GraphDuplicateJob = z.infer<typeof GraphDuplicateJobSchema>

/**
 * `GET /api/runs/<run_id>` für einen laufenden Kopierauftrag. Der Auftrag ist ein
 * Job der RunRegistry (`run_type='graph_duplicate'`), Fortschritt und Endzustand
 * kommen von dort — der Endpunkt hat keinen eigenen Statusabruf.
 *
 * Gespiegelt wird nur, was der Auftrag braucht; `RunDetail` (extra="allow")
 * trägt daneben Stage-, Budget- und Metadatenfelder, die hier nichts bedeuten.
 */
export const GraphDuplicateRunSchema = z
  .object({
    run_id: z.string().min(1),
    run_type: z.string().default(''),
    status: GraphDuplicateStatusSchema,
    progress: z.number().int().min(0).max(100).default(0),
    message: z.string().default(''),
    error: z.string().nullable().default(null),
    linked_ids: z
      .object({
        source_graph_id: z.string().default(''),
        graph_id: z.string().default(''),
        project_id: z.string().default(''),
      })
      .partial()
      .default({}),
  })
  .passthrough()
export type GraphDuplicateRun = z.infer<typeof GraphDuplicateRunSchema>

/** Zielzustände: danach wird nicht mehr gepollt. */
export const GRAPH_DUPLICATE_TERMINAL_STATUS: readonly GraphDuplicateStatus[] = [
  'completed',
  'failed',
  'stopped',
]

export function isGraphDuplicateTerminal(status: GraphDuplicateStatus): boolean {
  return GRAPH_DUPLICATE_TERMINAL_STATUS.includes(status)
}
