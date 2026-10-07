<script setup lang="ts">
/**
 * Bearbeitbare Graph-Ansicht (#1808, Etappe 8, ADR-0022).
 *
 * Aufbau wie der lesende Dreispalter (Etappe 2, `GraphReader`), mit drei
 * Erweiterungen:
 *  - ein Sperrband mit Grund statt eines deaktivierten Knopfes (Entscheid 3),
 *  - die Bearbeitungsspalte rechts (`GraphEditDetail`),
 *  - Herkunftsmarken an Liste und Tabelle; im Netz ist eine Handkante
 *    gestrichelt (`graphPanelData::manualEdgeDashPattern`).
 *
 * Der Zustand kommt aus zwei Composables, nicht aus dieser Komponente:
 * `useGraphLock` liefert den Sperrzustand, `useGraphEdit` die Schreibpfade.
 * Diese Komponente haelt nur Auswahl und Modus und meldet `changed`, damit die
 * aufrufende Ansicht die Graphdaten neu laedt — die Liste hier bleibt abgeleitet
 * und erfindet keine.
 *
 * Im Lauf bleibt die Ansicht lesend (Entscheid 9): dort wird diese Komponente
 * nicht benutzt, sondern `GraphReader`.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import GraphCanvas from '@/components/graph/GraphCanvas.vue'
import { buildEntityTypes } from '@/components/graph/graphPanelUtils'
import GraphReaderTable, { type TableTab } from '@/components/graph-library/GraphReaderTable.vue'
import { useGraphDuplicate } from '@/composables/graph-library/useGraphDuplicate'
import { useGraphEdit } from '@/composables/graph-library/useGraphEdit'
import { useGraphLock } from '@/composables/graph-library/useGraphLock'
import {
  filterEntities,
  filterRelations,
  typeOfNode,
  type GraphData,
  type ReaderEntity,
  type ReaderModel,
} from '@/composables/graph-library/graphReaderModel'
import { GraphEditTestId } from '@/contracts/testIds'
import type { EntityCreateArgs, RelationCreateArgs } from '@/api/graphEdit'
import type { EntityMerge, EntityUpdateInput, RelationUpdateInput } from '@/contracts/graphEditContract'
import GraphEditDetail, { type EditMode } from './GraphEditDetail.vue'
import GraphEditErrors from './GraphEditErrors.vue'
import GraphLockBanner from './GraphLockBanner.vue'
import GraphOriginMark from './GraphOriginMark.vue'
import { originOf } from './graphOrigin'

const LIST_CAP = 500

const props = defineProps<{
  model: ReaderModel
  graphData: GraphData
  ontologyTypes?: readonly string[]
  notice?: string | null
  /** Anzeigename des Graphen; Vorschlag fuer den Namen der Kopie. */
  graphName?: string | null
}>()

/** Nach jeder gelungenen Aktion neu laden: der Server ist die Quelle der Wahrheit. */
const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()
const route = useRoute()

const lock = useGraphLock(computed(() => props.model.graphId))
const edit = useGraphEdit(computed(() => props.model.graphId), lock)
// Ausweg aus der Sperre. Der Auftrag laeuft als Hintergrundjob; die Ansicht
// zeigt seinen Zustand, statt eine Kopie zu behaupten (Entscheid 3).
const duplicate = useGraphDuplicate(computed(() => props.model.graphId))

watch(
  () => props.model.graphId,
  (id) => {
    if (id) {
      void edit.loadOntologyTypes()
    }
  },
  { immediate: true },
)

const allowedEntityTypes = computed<string[]>(() => {
  const seen: string[] = []
  if (props.ontologyTypes) {
    for (const t of props.ontologyTypes) if (t && !seen.includes(t)) seen.push(t)
  }
  for (const t of edit.ontologyTypes.value) {
    if (t && !seen.includes(t)) seen.push(t)
  }
  for (const entity of props.model.entities) {
    if (entity.type && !seen.includes(entity.type)) seen.push(entity.type)
  }
  return seen
})

const editable = computed(() => lock.editable.value)
const busy = computed(() => edit.busy.value)

/**
 * Vorschlag fuer den Namen der Kopie. Ohne Anzeigename (der Leser kennt nur
 * die `graph_id`) faellt der Name auf den Graphen selbst zurueck — der Vertrag
 * verlangt einen, und ein leerer Name wuerde den Auftrag nur scheitern lassen.
 */
const duplicateName = computed(() => props.graphName?.trim() || props.model.graphId)

const view = ref<'net' | 'table'>('net')
const tableTab = ref<TableTab>('entities')
const mode = ref<EditMode>('view')
const query = ref('')
const activeTypes = ref<Set<string>>(new Set())
const selectedEntityId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)
const done = ref<string | null>(null)

const entitiesById = computed(() => new Map(props.model.entities.map((entity) => [entity.id, entity])))
const relationsById = computed(() => new Map(props.model.relations.map((relation) => [relation.id, relation])))
const selectedEntity = computed(() =>
  selectedEntityId.value ? (entitiesById.value.get(selectedEntityId.value) ?? null) : null,
)
const selectedRelation = computed(() =>
  !selectedEntity.value && selectedEdgeId.value ? (relationsById.value.get(selectedEdgeId.value) ?? null) : null,
)
const filteredEntities = computed(() =>
  filterEntities(props.model.entities, { query: query.value, types: activeTypes.value }),
)
const filteredIds = computed(() => new Set(filteredEntities.value.map((entity) => entity.id)))
const filteredRelations = computed(() => filterRelations(props.model.relations, filteredIds.value, ''))
const listedEntities = computed(() => filteredEntities.value.slice(0, LIST_CAP))
const glyphByType = computed(() => new Map(props.model.types.map((type) => [type.name, type.glyph])))

/** Netz: nur der Typfilter greift auf den Graphen, die Suche auf Liste und Tabelle. */
const netData = computed<GraphData>(() => {
  if (activeTypes.value.size === 0) return props.graphData
  const keep = new Set(
    props.graphData.nodes.filter((node) => activeTypes.value.has(typeOfNode(node.labels, node.entity_type))).map((node) => node.uuid),
  )
  return {
    ...props.graphData,
    nodes: props.graphData.nodes.filter((node) => keep.has(node.uuid)),
    edges: props.graphData.edges.filter((edge) => keep.has(edge.source_node_uuid) && keep.has(edge.target_node_uuid)),
  }
})
const netTypes = computed(() => buildEntityTypes(netData.value as { nodes?: Array<Record<string, unknown>> }))

function toggleType(name: string): void {
  const next = new Set(activeTypes.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  activeTypes.value = next
}

function selectEntity(id: string): void {
  selectedEntityId.value = id
  selectedEdgeId.value = null
  mode.value = 'view'
}

function selectEdge(id: string): void {
  selectedEdgeId.value = id
  selectedEntityId.value = null
  mode.value = 'view'
  tableTab.value = 'relations'
}

function onNetSelect(item: { type: string; data: { uuid?: string } } | null): void {
  if (!item?.data?.uuid) return
  if (item.type === 'node') selectEntity(item.data.uuid)
  else if (item.type === 'edge') selectEdge(item.data.uuid)
}

// Aus dem Bericht kommende Sprünge (`?entity=`/`?edge=`) waehlen wie im Leser.
watch(
  () => [route.query['entity'], route.query['edge'], props.model.graphId],
  () => {
    const rawEntity = route.query['entity']
    const rawEdge = route.query['edge']
    const entityParam = typeof rawEntity === 'string' ? rawEntity : ''
    const edgeParam = typeof rawEdge === 'string' ? rawEdge : ''
    if (edgeParam && relationsById.value.has(edgeParam)) selectEdge(edgeParam)
    else if (entityParam) {
      const byId = entitiesById.value.get(entityParam)
      const hit =
        byId ?? props.model.entities.find((e) => e.name.toLocaleLowerCase('de') === entityParam.toLocaleLowerCase('de'))
      if (hit) selectEntity(hit.id)
    }
  },
  { immediate: true },
)

// --- Aktionen --------------------------------------------------------------

async function after<T>(result: T | null, message: string | null): Promise<void> {
  if (result === null) return
  done.value = message
  emit('changed')
}

async function onCreateEntity(args: { name: string; entity_type: string; summary?: string; aliases: string[] }): Promise<void> {
  await after(await edit.createEntity(args as EntityCreateArgs), t('views.graphEdit.view.done'))
}

async function onUpdateEntity(uuid: string, patch: EntityUpdateInput): Promise<void> {
  await after(await edit.updateEntity(uuid, patch), t('views.graphEdit.view.done'))
}

async function onDeleteEntity(uuid: string): Promise<void> {
  const result = await edit.deleteEntity(uuid)
  if (result === null) return
  selectEntity('') // Auswahl verliert ihren Gegenstand.
  selectedEntityId.value = null
  done.value = t('views.graphEdit.view.entity.deleted', { n: result.removed_relation_count })
  emit('changed')
}

async function onMerge(args: EntityMerge): Promise<void> {
  const result = await edit.mergeEntities(args)
  if (result === null) return
  selectedEntityId.value = null
  done.value = t('views.graphEdit.view.merge.result', {
    n: result.rewired_relation_count,
    d: result.dropped_relation_count,
  })
  emit('changed')
}

async function onCreateRelation(args: { source_uuid: string; target_uuid: string; name: string; fact: string }): Promise<void> {
  await after(await edit.createRelation(args as RelationCreateArgs), t('views.graphEdit.view.done'))
}

async function onUpdateRelation(uuid: string, patch: RelationUpdateInput): Promise<void> {
  await after(await edit.updateRelation(uuid, patch), t('views.graphEdit.view.done'))
}

async function onDeleteRelation(uuid: string): Promise<void> {
  const result = await edit.deleteRelation(uuid)
  if (result === null) return
  selectedEdgeId.value = null
  done.value = t('views.graphEdit.view.relation.deleted')
  emit('changed')
}

/** Startet den Kopierauftrag. Der Auftrag gehoert einem anderen Graphen: die
 *  angezeigten Knoten und Kanten bleiben unberuehrt, ein `changed` gibt es
 *  erst mit der fertigen Kopie (und dann an deren eigenem Ort). */
async function onDuplicate(name: string): Promise<void> {
  await duplicate.start(name)
}

const viewOptions = ['net', 'table'] as const

function originMark(entity: ReaderEntity): ReturnType<typeof originOf> {
  return originOf(entity.raw)
}
</script>

<template>
  <section class="gev" :aria-label="t('views.graphEdit.view.label')" :data-testid="GraphEditTestId.root">
    <GraphLockBanner
      :status="lock.status.value"
      :used-by="lock.usedBy.value"
      :loading="lock.loading.value"
      :error="lock.error.value"
      :duplicate="duplicate"
      :duplicate-name="duplicateName"
      @reload="lock.reload()"
      @duplicate="onDuplicate"
    />

    <GraphEditErrors :failure="edit.error.value" @dismiss="edit.clearError()" />

    <p v-if="notice" class="gev__notice" role="status">{{ notice }}</p>
    <p v-if="done" class="gev__notice" role="status" :data-testid="GraphEditTestId.notice">{{ done }}</p>

    <div class="gev__grid">
      <div class="gev__left">
        <label class="gev__search">
          <span class="gev__label">{{ t('views.graphLibrary.reader.search.label') }}</span>
          <input
            v-model="query"
            type="search"
            class="gev__input"
            :placeholder="t('views.graphLibrary.reader.search.placeholder')"
          />
        </label>

        <div class="gev__group" role="group" :aria-label="t('views.graphLibrary.reader.types.label')">
          <div class="gev__row">
            <span class="gev__label">{{ t('views.graphLibrary.reader.types.title') }}</span>
            <button
              v-if="activeTypes.size > 0"
              type="button"
              class="gev__link"
              @click="activeTypes = new Set()"
            >
              {{ t('views.graphLibrary.reader.types.clear') }}
            </button>
          </div>
          <ul class="gev__types">
            <li v-for="type in model.types" :key="type.name">
              <button
                type="button"
                class="gev__type"
                :aria-pressed="activeTypes.has(type.name)"
                :data-type="type.name"
                @click="toggleType(type.name)"
              >
                <span aria-hidden="true" class="gev__check">{{ activeTypes.has(type.name) ? '✓' : '' }}</span>
                <span aria-hidden="true" class="gev__glyph">{{ type.glyph }}</span>
                <span>{{ type.name }}</span>
                <span class="gev__num">{{ type.count }}</span>
              </button>
            </li>
          </ul>
        </div>

        <div class="gev__group">
          <h2 class="gev__label">
            {{ t('views.graphLibrary.reader.list.title') }}
            <span class="gev__num" data-testid="gev-list-count">{{ filteredEntities.length }}</span>
          </h2>
          <p v-if="filteredEntities.length === 0" class="gev__empty" role="status">
            {{ t('views.graphLibrary.reader.list.empty') }}
          </p>
          <ul v-else class="gev__list" :aria-label="t('views.graphLibrary.reader.list.title')">
            <li v-for="entity in listedEntities" :key="entity.id" :data-entity-id="entity.id">
              <button
                type="button"
                class="gev__item"
                :class="{ 'gev__item--on': entity.id === selectedEntityId }"
                :aria-current="entity.id === selectedEntityId ? 'true' : undefined"
                @click="selectEntity(entity.id)"
              >
                <span aria-hidden="true" class="gev__glyph">{{ glyphByType.get(entity.type) }}</span>
                <span class="gev__itemname">{{ entity.name }}</span>
                <GraphOriginMark v-if="originMark(entity)" :origin="originMark(entity)" />
              </button>
            </li>
          </ul>
        </div>
      </div>

      <div class="gev__mid">
        <div class="gev__bar">
          <div
            class="gev__seg"
            role="group"
            :aria-label="t('views.graphEdit.view.label')"
            :data-testid="GraphEditTestId.viewToggle"
          >
            <button
              v-for="option in viewOptions"
              :key="option"
              type="button"
              class="gev__segbtn"
              :aria-pressed="view === option"
              :data-testid="option === 'net' ? GraphEditTestId.viewNet : GraphEditTestId.viewTable"
              @click="view = option"
            >
              {{ t(`views.graphEdit.view.${option}`) }}
            </button>
          </div>

          <!-- Ohne gesicherten Sperrzustand gibt es keine Schreibwege, auch nicht als Knopf. -->
          <div v-if="editable" class="gev__tools" :data-testid="GraphEditTestId.toolbar">
            <button
              type="button"
              class="gev__btn gev__btn--primary"
              :data-testid="GraphEditTestId.createEntity"
              :disabled="busy"
              @click="mode = 'create-entity'"
            >
              {{ t('views.graphEdit.view.entity.createTitle') }}
            </button>
            <button
              type="button"
              class="gev__btn"
              :data-testid="GraphEditTestId.createRelation"
              :disabled="busy"
              @click="mode = 'create-relation'"
            >
              {{ t('views.graphEdit.view.relation.createTitle') }}
            </button>
          </div>
        </div>

        <p class="gev__legend">{{ t('views.graphEdit.view.legend') }}</p>

        <div v-if="view === 'net'" class="gev__net" :data-testid="GraphEditTestId.net">
          <GraphCanvas
            :graph-data="netData"
            :entity-types="netTypes"
            :hide-detail="true"
            @select="onNetSelect"
          />
        </div>
        <div v-else :data-testid="GraphEditTestId.table">
          <GraphReaderTable
            v-model:tab="tableTab"
            :entities="filteredEntities"
            :relations="filteredRelations"
            :types="model.types"
            :selected-entity-id="selectedEntityId"
            :selected-edge-id="selectedEdgeId"
            show-origin
            @select-entity="(id: string) => selectEntity(id)"
            @select-edge="(id: string) => selectEdge(id)"
          />
        </div>
      </div>

      <GraphEditDetail
        class="gev__right"
        :entity="selectedEntity"
        :relation="selectedRelation"
        :entities="model.entities"
        :relations="model.relations"
        :ontology-types="allowedEntityTypes"
        :editable="editable"
        :busy="busy"
        :mode="mode"
        @mode="mode = $event"
        @update-entity="onUpdateEntity"
        @create-entity="onCreateEntity"
        @delete-entity="onDeleteEntity"
        @merge="onMerge"
        @update-relation="onUpdateRelation"
        @create-relation="onCreateRelation"
        @delete-relation="onDeleteRelation"
      />
    </div>
  </section>
</template>

<style scoped>
.gev {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.gev__notice {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font-size: 13px;
}

.gev__grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(280px, 380px);
  gap: 16px;
  align-items: start;
}

@media (max-width: 1023px) {
  .gev__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.gev__left,
.gev__mid {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.gev__search {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gev__label {
  display: flex;
  gap: 8px;
  margin: 0;
  color: var(--fg2);
  font-size: 12.5px;
  font-weight: 600;
}

.gev__input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
}

.gev__group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gev__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gev__link {
  border: none;
  background: transparent;
  color: var(--acc-text);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  padding: 2px 4px;
}

.gev__types,
.gev__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.gev__list {
  max-height: 360px;
  overflow: auto;
}

.gev__type,
.gev__item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 4px 8px;
  border: none;
  border-radius: var(--ag-r-6);
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  text-align: left;
  cursor: pointer;
}

.gev__type:hover,
.gev__item:hover {
  background: var(--s3);
}

.gev__item--on {
  background: var(--acc-soft);
  font-weight: 650;
}

.gev__check {
  display: inline-block;
  width: 1em;
  color: var(--acc-text);
  font-weight: 700;
}

.gev__glyph {
  color: var(--fg2);
}

.gev__itemname {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.gev__num {
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
  font-weight: 400;
}

.gev__empty {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}

.gev__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.gev__seg {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
}

.gev__segbtn {
  height: 28px;
  padding: 0 14px;
  border: none;
  border-radius: var(--ag-r-6);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.gev__segbtn[aria-pressed='true'] {
  background: var(--s2);
  color: var(--fg);
  box-shadow: inset 0 -2px 0 var(--acc);
}

.gev__tools {
  display: flex;
  gap: 8px;
}

.gev__btn {
  min-height: 30px;
  padding: 4px 12px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.gev__btn--primary {
  background: var(--acc);
  color: var(--on-acc);
}

.gev__btn:disabled {
  cursor: progress;
  color: var(--fg2);
}

.gev__legend {
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
}

.gev__net {
  position: relative;
  height: clamp(360px, 60vh, 720px);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  overflow: hidden;
}

.gev__input:focus-visible,
.gev__btn:focus-visible,
.gev__type:focus-visible,
.gev__item:focus-visible,
.gev__segbtn:focus-visible,
.gev__link:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
</style>
