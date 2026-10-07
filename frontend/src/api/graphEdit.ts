/**
 * Graph bearbeiten (#1808, Etappe 8, ADR-0022): Sperrzustand, Entitäten und
 * Beziehungen von Hand anlegen, ändern, löschen, Entitäten zusammenführen.
 * Jede Anfrage läuft vor dem Senden, jede Antwort nach dem Empfang durch ein
 * Zod-Schema (`contracts/graphEditContract`).
 *
 * Fehlerbild des Backends (`backend/app/api/graph_edit.py`):
 * - 409 `graph_locked` (mit `used_by`)       -> `GraphLockedError`
 * - 409 `graph_edit_conflict`                -> `GraphEditConflictError`
 * - 409 `embedding_migration_running`        -> `EmbeddingMigrationRunningError`
 * - 503 (Einbettung fehlgeschlagen, nichts geschrieben) -> `GraphEditEmbeddingFailedError`
 * Alles andere (400, 404, Transport) bleibt der `ApiError` des Interceptors.
 *
 * Das Duplizieren (`GraphDuplicateRequest`/`GraphDuplicateJob`) ist im Vertrag
 * gespiegelt; die Client-Funktion folgt mit dem Endpunkt.
 */
import type { z } from 'zod'
import service from './index'
import { ApiError } from './envelope'
import { readEnvelope } from '@/composables/run/simulation/simulationEnvelope'
import {
  EntityCreateSchema,
  EntityDeleteResultSchema,
  EntityMergeResultSchema,
  EntityMergeSchema,
  EntityUpdateSchema,
  GraphLockStateSchema,
  GraphLockUserSchema,
  GraphNodeViewSchema,
  GraphEdgeViewSchema,
  RelationCreateSchema,
  RelationDeleteResultSchema,
  RelationUpdateSchema,
  type EntityCreateInput,
  type EntityDeleteResult,
  type EntityMerge,
  type EntityMergeResult,
  type EntityUpdateInput,
  type GraphEdgeView,
  type GraphLockState,
  type GraphLockUser,
  type GraphNodeView,
  type RelationCreateInput,
  type RelationDeleteResult,
  type RelationUpdateInput,
} from '@/contracts/graphEditContract'

// ---------------------------------------------------------------------------
// Fehler
// ---------------------------------------------------------------------------

export class GraphEditApiError extends Error {
  readonly code: string
  readonly status: number
  constructor(message: string, code: string, status: number) {
    super(message)
    this.name = 'GraphEditApiError'
    this.code = code
    this.status = status
  }
}

/** 409: eine Simulation verwendet den Graphen. */
export class GraphLockedError extends GraphEditApiError {
  readonly usedBy: GraphLockUser[]
  constructor(message: string, usedBy: GraphLockUser[]) {
    super(message, 'graph_locked', 409)
    this.name = 'GraphLockedError'
    this.usedBy = usedBy
  }
}

/** 409: die Änderung kollidiert mit einem bestehenden Element. */
export class GraphEditConflictError extends GraphEditApiError {
  constructor(message: string) {
    super(message, 'graph_edit_conflict', 409)
    this.name = 'GraphEditConflictError'
  }
}

/** 409: eine Embedding-Migration läuft, der Graph ist vorübergehend nicht bearbeitbar. */
export class EmbeddingMigrationRunningError extends GraphEditApiError {
  constructor(message: string) {
    super(message, 'embedding_migration_running', 409)
    this.name = 'EmbeddingMigrationRunningError'
  }
}

/** 503: die Einbettung konnte nicht berechnet werden; es wurde nichts geändert. */
export class GraphEditEmbeddingFailedError extends GraphEditApiError {
  constructor(message: string) {
    super(message, 'service_unavailable', 503)
    this.name = 'GraphEditEmbeddingFailedError'
  }
}

/** Die Eingabe verletzt den Vertrag; es wurde nichts gesendet. */
export class GraphEditInputError extends Error {
  readonly issues: z.core.$ZodIssue[]
  constructor(label: string, issues: z.core.$ZodIssue[]) {
    super(`Ungültige Eingabe ${label}: ${issues.map((i) => i.message).join('; ')}`)
    this.name = 'GraphEditInputError'
    this.issues = issues
  }
}

export type GraphEditTypedError =
  | GraphLockedError
  | GraphEditConflictError
  | EmbeddingMigrationRunningError
  | GraphEditEmbeddingFailedError

export function isGraphEditTypedError(value: unknown): value is GraphEditTypedError {
  return (
    value instanceof GraphLockedError ||
    value instanceof GraphEditConflictError ||
    value instanceof EmbeddingMigrationRunningError ||
    value instanceof GraphEditEmbeddingFailedError
  )
}

function usedByOf(err: ApiError): GraphLockUser[] {
  const body = err.originalResponse as { used_by?: unknown } | undefined
  const parsed = GraphLockUserSchema.array().safeParse(body?.used_by)
  return parsed.success ? parsed.data : []
}

function mapError(err: unknown): unknown {
  if (!(err instanceof ApiError)) return err
  if (err.status === 409 && err.code === 'graph_locked') return new GraphLockedError(err.message, usedByOf(err))
  if (err.status === 409 && err.code === 'graph_edit_conflict') return new GraphEditConflictError(err.message)
  if (err.status === 409 && err.code === 'embedding_migration_running') {
    return new EmbeddingMigrationRunningError(err.message)
  }
  // Status 0 ist ein Transportfehler (Backend offline), kein Embedding-Fehler.
  if (err.status === 503) return new GraphEditEmbeddingFailedError(err.message)
  return err
}

async function call<T>(request: () => Promise<unknown>, data: z.ZodType<T>, label: string): Promise<T> {
  let raw: unknown
  try {
    raw = await request()
  } catch (err) {
    throw mapError(err)
  }
  return readEnvelope(raw, data, label) as T
}

function parseInput<S extends z.ZodType>(schema: S, value: unknown, label: string): z.output<S> {
  const parsed = schema.safeParse(value)
  if (!parsed.success) throw new GraphEditInputError(label, parsed.error.issues)
  return parsed.data
}

function base(graphId: string): string {
  return `/api/graph/${encodeURIComponent(graphId)}`
}

function segment(uuid: string): string {
  return encodeURIComponent(uuid)
}

// ---------------------------------------------------------------------------
// Aufrufe
// ---------------------------------------------------------------------------

export function getGraphLock(graphId: string): Promise<GraphLockState> {
  return call(() => service.get(`${base(graphId)}/lock`), GraphLockStateSchema, 'graph/lock')
}

export type EntityCreateArgs = Omit<EntityCreateInput, 'client_request_id'> & { client_request_id?: string }
export type RelationCreateArgs = Omit<RelationCreateInput, 'client_request_id'> & { client_request_id?: string }

/**
 * Legt eine Entität an. Ohne `client_request_id` erzeugt der Client eine
 * (`crypto.randomUUID()`); wer einen Versuch wiederholt, übergibt dieselbe.
 */
export async function createEntity(graphId: string, args: EntityCreateArgs): Promise<GraphNodeView> {
  const body = parseInput(
    EntityCreateSchema,
    { ...args, client_request_id: args.client_request_id ?? crypto.randomUUID() },
    'entities',
  )
  return call(() => service.post(`${base(graphId)}/entities`, body), GraphNodeViewSchema, 'graph/entities')
}

export async function updateEntity(graphId: string, entityUuid: string, patch: EntityUpdateInput): Promise<GraphNodeView> {
  const body = parseInput(EntityUpdateSchema, patch, 'entities/update')
  return call(
    () => service.patch(`${base(graphId)}/entities/${segment(entityUuid)}`, body),
    GraphNodeViewSchema,
    'graph/entities/update',
  )
}

export function deleteEntity(graphId: string, entityUuid: string): Promise<EntityDeleteResult> {
  return call(
    () => service.delete(`${base(graphId)}/entities/${segment(entityUuid)}`),
    EntityDeleteResultSchema,
    'graph/entities/delete',
  )
}

export async function mergeEntities(graphId: string, args: EntityMerge): Promise<EntityMergeResult> {
  const body = parseInput(EntityMergeSchema, args, 'entities/merge')
  return call(
    () => service.post(`${base(graphId)}/entities/merge`, body),
    EntityMergeResultSchema,
    'graph/entities/merge',
  )
}

export async function createRelation(graphId: string, args: RelationCreateArgs): Promise<GraphEdgeView> {
  const body = parseInput(
    RelationCreateSchema,
    { ...args, client_request_id: args.client_request_id ?? crypto.randomUUID() },
    'relations',
  )
  return call(() => service.post(`${base(graphId)}/relations`, body), GraphEdgeViewSchema, 'graph/relations')
}

export async function updateRelation(
  graphId: string,
  relationUuid: string,
  patch: RelationUpdateInput,
): Promise<GraphEdgeView> {
  const body = parseInput(RelationUpdateSchema, patch, 'relations/update')
  return call(
    () => service.patch(`${base(graphId)}/relations/${segment(relationUuid)}`, body),
    GraphEdgeViewSchema,
    'graph/relations/update',
  )
}

export function deleteRelation(graphId: string, relationUuid: string): Promise<RelationDeleteResult> {
  return call(
    () => service.delete(`${base(graphId)}/relations/${segment(relationUuid)}`),
    RelationDeleteResultSchema,
    'graph/relations/delete',
  )
}
