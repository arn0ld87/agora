/**
 * Bearbeitungs-Aktionen eines Graphen (#1808, Etappe 8, ADR-0022).
 *
 * Jede Aktion setzt `busy`, liefert bei Erfolg das geaenderte Element und bei
 * einem Fehler `null`; der Fehler steht dann strukturiert in `error`. Die
 * Oberflaeche uebersetzt ueber `error.kind` (i18n `views.graphEdit.errors.*`),
 * `error.message` ist der Text des Backends.
 *
 * 409 `graph_locked` setzt zusaetzlich den uebergebenen Sperrzustand
 * (`lock.markLocked`), damit die Oberflaeche die Sperre sichtbar zeigt.
 */
import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import {
  EmbeddingMigrationRunningError,
  GraphEditConflictError,
  GraphEditEmbeddingFailedError,
  GraphEditInputError,
  GraphLockedError,
  createEntity,
  createRelation,
  deleteEntity,
  deleteRelation,
  mergeEntities,
  updateEntity,
  updateRelation,
  type EntityCreateArgs,
  type RelationCreateArgs,
} from '@/api/graphEdit'
import type {
  EntityDeleteResult,
  EntityMerge,
  EntityMergeResult,
  EntityUpdateInput,
  GraphEdgeView,
  GraphLockUser,
  GraphNodeView,
  RelationDeleteResult,
  RelationUpdateInput,
} from '@/contracts/graphEditContract'

export type GraphEditErrorKind =
  | 'locked'
  | 'conflict'
  | 'migration_running'
  | 'embedding_failed'
  | 'invalid_input'
  | 'other'

export interface GraphEditFailure {
  kind: GraphEditErrorKind
  message: string
  /** Nur bei `locked`: die Simulationen, die den Graphen verwenden. */
  usedBy: GraphLockUser[]
}

export function classifyGraphEditError(caught: unknown): GraphEditFailure {
  const message = caught instanceof Error && caught.message ? caught.message : String(caught)
  if (caught instanceof GraphLockedError) return { kind: 'locked', message, usedBy: caught.usedBy }
  if (caught instanceof GraphEditConflictError) return { kind: 'conflict', message, usedBy: [] }
  if (caught instanceof EmbeddingMigrationRunningError) return { kind: 'migration_running', message, usedBy: [] }
  if (caught instanceof GraphEditEmbeddingFailedError) return { kind: 'embedding_failed', message, usedBy: [] }
  if (caught instanceof GraphEditInputError) return { kind: 'invalid_input', message, usedBy: [] }
  return { kind: 'other', message, usedBy: [] }
}

export interface GraphEditLockSink {
  markLocked: (users: GraphLockUser[]) => void
}

export function useGraphEdit(
  graphId: MaybeRefOrGetter<string | null | undefined>,
  lock?: GraphEditLockSink,
) {
  const busy = ref(false)
  const error = ref<GraphEditFailure | null>(null)

  async function run<T>(action: (id: string) => Promise<T>): Promise<T | null> {
    const id = toValue(graphId)
    if (!id) {
      error.value = { kind: 'other', message: 'graph_id fehlt', usedBy: [] }
      return null
    }
    busy.value = true
    error.value = null
    try {
      return await action(id)
    } catch (caught) {
      const failure = classifyGraphEditError(caught)
      error.value = failure
      if (failure.kind === 'locked') lock?.markLocked(failure.usedBy)
      return null
    } finally {
      busy.value = false
    }
  }

  function clearError(): void {
    error.value = null
  }

  return {
    busy,
    error,
    clearError,
    createEntity: (args: EntityCreateArgs): Promise<GraphNodeView | null> => run((id) => createEntity(id, args)),
    updateEntity: (uuid: string, patch: EntityUpdateInput): Promise<GraphNodeView | null> =>
      run((id) => updateEntity(id, uuid, patch)),
    deleteEntity: (uuid: string): Promise<EntityDeleteResult | null> => run((id) => deleteEntity(id, uuid)),
    mergeEntities: (args: EntityMerge): Promise<EntityMergeResult | null> => run((id) => mergeEntities(id, args)),
    createRelation: (args: RelationCreateArgs): Promise<GraphEdgeView | null> =>
      run((id) => createRelation(id, args)),
    updateRelation: (uuid: string, patch: RelationUpdateInput): Promise<GraphEdgeView | null> =>
      run((id) => updateRelation(id, uuid, patch)),
    deleteRelation: (uuid: string): Promise<RelationDeleteResult | null> => run((id) => deleteRelation(id, uuid)),
  }
}
