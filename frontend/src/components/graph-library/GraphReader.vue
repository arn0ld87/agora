<script setup lang="ts">
/**
 * GraphReader (#1797, Etappe 2): lesende Graph-Ansicht fuer Lauf und Bibliothek.
 * Dreispaltig nach Bauplan 4.3: links Suche, Typfilter und Entitaetenliste,
 * Mitte Netz oder Tabelle, rechts Detail der Auswahl. Unter 1024 px stapelt
 * sich alles in dieser Reihenfolge einspaltig. Das Bearbeiten hat Etappe 8
 * (`GraphEditView`); dieser Leser zeigt nur noch die Herkunftsmarken, damit
 * eine Handkante auch im Lauf erkennbar bleibt (ADR-0022 §5).
 *
 * `?entity=` (uuid oder Name) und `?edge=` (uuid) waehlen und zentrieren das Ziel.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GraphCanvas from '@/components/graph/GraphCanvas.vue'
import { buildEntityTypes } from '@/components/graph/graphPanelUtils'
import { exportGraphMl } from '@/api/graph'
import {
  filterEntities,
  filterRelations,
  typeOfNode,
  type GraphData,
  type ReaderModel,
} from '@/composables/graph-library/graphReaderModel'
import GraphOriginMark from '@/components/graph-edit/GraphOriginMark.vue'
import { originOf } from '@/components/graph-edit/graphOrigin'
import GraphReaderDetail from './GraphReaderDetail.vue'
import GraphReaderTable, { type TableTab } from './GraphReaderTable.vue'

const LIST_CAP = 500

const props = defineProps<{
  model: ReaderModel
  graphData: GraphData
  /** Hinweis oben im Leser, z. B. „Teilgraph“ bei abgebrochenem Build. */
  notice?: string | null
}>()

const { t } = useI18n()
const route = useRoute()

interface CanvasHandle {
  focusTarget: (target: { nodeId?: string | null; edgeSource?: string | null; edgeTarget?: string | null }) => boolean
}
const canvasRef = ref<CanvasHandle | null>(null)

const view = ref<'net' | 'table'>('net')
const tableTab = ref<TableTab>('entities')
const query = ref('')
const activeTypes = ref<Set<string>>(new Set())
const selectedEntityId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)
const targetMissing = ref(false)
const exporting = ref(false)
const exportError = ref('')

const glyphByType = computed(() => new Map(props.model.types.map((type) => [type.name, type.glyph])))
const entitiesById = computed(() => new Map(props.model.entities.map((e) => [e.id, e])))
const relationsById = computed(() => new Map(props.model.relations.map((r) => [r.id, r])))

const filteredEntities = computed(() =>
  filterEntities(props.model.entities, { query: query.value, types: activeTypes.value }),
)
const filteredIds = computed(() => new Set(filteredEntities.value.map((e) => e.id)))
const filteredRelations = computed(() => filterRelations(props.model.relations, filteredIds.value, ''))
const listedEntities = computed(() => filteredEntities.value.slice(0, LIST_CAP))

const selectedEntity = computed(() =>
  selectedEntityId.value ? (entitiesById.value.get(selectedEntityId.value) ?? null) : null,
)
const selectedRelation = computed(() =>
  !selectedEntity.value && selectedEdgeId.value ? (relationsById.value.get(selectedEdgeId.value) ?? null) : null,
)
const entityRelations = computed(() =>
  selectedEntity.value
    ? props.model.relations.filter((r) => r.fromId === selectedEntity.value?.id || r.toId === selectedEntity.value?.id)
    : [],
)

/** Netz: nur der Typfilter wirkt auf den Graphen, die Suche auf Liste und Tabelle. */
const netData = computed<GraphData>(() => {
  if (activeTypes.value.size === 0) return props.graphData
  const keep = new Set(
    props.graphData.nodes.filter((n) => activeTypes.value.has(typeOfNode(n.labels))).map((n) => n.uuid),
  )
  return {
    ...props.graphData,
    nodes: props.graphData.nodes.filter((n) => keep.has(n.uuid)),
    edges: props.graphData.edges.filter((e) => keep.has(e.source_node_uuid) && keep.has(e.target_node_uuid)),
  }
})
const netTypes = computed(() => buildEntityTypes(netData.value as { nodes?: Array<Record<string, unknown>> }))

function toggleType(name: string): void {
  const next = new Set(activeTypes.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  activeTypes.value = next
}

function clearTypes(): void {
  activeTypes.value = new Set()
}

function focus(target: { nodeId?: string; edgeSource?: string; edgeTarget?: string }): void {
  if (view.value !== 'net') return
  void nextTick(() => canvasRef.value?.focusTarget(target))
}

function selectEntity(id: string, options: { focusNet?: boolean } = {}): void {
  selectedEntityId.value = id
  selectedEdgeId.value = null
  targetMissing.value = false
  if (options.focusNet !== false) focus({ nodeId: id })
}

function selectEdge(id: string, options: { focusNet?: boolean } = {}): void {
  selectedEdgeId.value = id
  selectedEntityId.value = null
  targetMissing.value = false
  tableTab.value = 'relations'
  const rel = relationsById.value.get(id)
  if (rel && options.focusNet !== false) focus({ edgeSource: rel.fromId, edgeTarget: rel.toId })
}

function onNetSelect(item: { type: string; data: { uuid?: string } } | null): void {
  if (!item?.data?.uuid) return
  if (item.type === 'node') selectEntity(item.data.uuid, { focusNet: false })
  else if (item.type === 'edge') selectEdge(item.data.uuid, { focusNet: false })
}

function applyRouteTarget(): void {
  const rawEntity = route.query['entity']
  const rawEdge = route.query['edge']
  const entityParam = typeof rawEntity === 'string' ? rawEntity : ''
  const edgeParam = typeof rawEdge === 'string' ? rawEdge : ''
  if (!entityParam && !edgeParam) {
    targetMissing.value = false
    return
  }
  // Die Auswahl soll sichtbar sein: Filter zuruecksetzen.
  query.value = ''
  clearTypes()
  if (edgeParam) {
    if (relationsById.value.has(edgeParam)) {
      selectEdge(edgeParam)
      return
    }
  }
  if (entityParam) {
    const byId = entitiesById.value.get(entityParam)
    const byName = byId
      ? null
      : props.model.entities.find((e) => e.name.toLocaleLowerCase('de') === entityParam.toLocaleLowerCase('de'))
    const hit = byId ?? byName
    if (hit) {
      selectEntity(hit.id)
      return
    }
  }
  targetMissing.value = true
}

watch(
  () => [route.query['entity'], route.query['edge'], props.model.graphId],
  () => applyRouteTarget(),
  { immediate: true },
)

// Beim Wechsel Tabelle -> Netz die Auswahl im Netz zentrieren.
watch(view, (next) => {
  if (next !== 'net') return
  if (selectedEntityId.value) focus({ nodeId: selectedEntityId.value })
  else if (selectedRelation.value) focus({ edgeSource: selectedRelation.value.fromId, edgeTarget: selectedRelation.value.toId })
})

async function exportGraphml(): Promise<void> {
  exporting.value = true
  exportError.value = ''
  try {
    // The API interceptor already unwraps the Blob; reading .data again loses its bytes.
    const blob = await exportGraphMl(props.graphData.graph_id)
    if (!(blob instanceof Blob) || blob.size === 0) {
      throw new Error('GraphML export was empty')
    }
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `agora-graph-${props.graphData.graph_id}.graphml`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setTimeout(() => URL.revokeObjectURL(url), 500)
  } catch (caught) {
    exportError.value = caught instanceof Error && caught.message ? caught.message : t('views.graphLibrary.reader.export.failed')
  } finally {
    exporting.value = false
  }
}

const viewOptions = ['net', 'table'] as const
</script>

<template>
  <section class="gr" :aria-label="t('views.graphLibrary.reader.label')">
    <header class="gr__head">
      <p class="gr__counts" data-testid="gr-counts">
        {{ t('views.graphLibrary.reader.counts', { entities: model.entities.length, relations: model.relations.length }) }}
      </p>
      <span class="gr__spacer" />
      <div v-if="$slots.actions" class="gr__actions"><slot name="actions" /></div>
      <button type="button" class="gr__btn" :disabled="exporting" @click="exportGraphml">
        {{ exporting ? t('views.graphLibrary.reader.export.running') : t('views.graphLibrary.reader.export.graphml') }}
      </button>
    </header>

    <p v-if="notice" class="gr__notice" role="status">{{ notice }}</p>
    <p v-if="exportError" class="gr__notice gr__notice--err" role="alert">{{ exportError }}</p>
    <p v-if="targetMissing" class="gr__notice gr__notice--warn" role="status" data-testid="gr-target-missing">
      {{ t('views.graphLibrary.reader.targetMissing') }}
    </p>

    <div class="gr__grid">
      <div class="gr__left">
        <label class="gr__search">
          <span class="gr__label">{{ t('views.graphLibrary.reader.search.label') }}</span>
          <input
            v-model="query"
            type="search"
            class="gr__input"
            :placeholder="t('views.graphLibrary.reader.search.placeholder')"
          />
        </label>

        <div class="gr__group" role="group" :aria-label="t('views.graphLibrary.reader.types.label')">
          <div class="gr__row">
            <span class="gr__label">{{ t('views.graphLibrary.reader.types.title') }}</span>
            <button v-if="activeTypes.size > 0" type="button" class="gr__link" @click="clearTypes">
              {{ t('views.graphLibrary.reader.types.clear') }}
            </button>
          </div>
          <ul class="gr__types">
            <li v-for="type in model.types" :key="type.name">
              <button
                type="button"
                class="gr__type"
                :aria-pressed="activeTypes.has(type.name)"
                :data-type="type.name"
                @click="toggleType(type.name)"
              >
                <span aria-hidden="true" class="gr__check">{{ activeTypes.has(type.name) ? '✓' : '' }}</span>
                <span aria-hidden="true" class="gr__glyph">{{ type.glyph }}</span>
                <span class="gr__typename">{{ type.name }}</span>
                <span class="gr__num">{{ type.count }}</span>
              </button>
            </li>
          </ul>
        </div>

        <div class="gr__group">
          <h2 class="gr__label gr__label--h">
            {{ t('views.graphLibrary.reader.list.title') }}
            <span class="gr__num" data-testid="gr-list-count">{{ filteredEntities.length }}</span>
          </h2>
          <p v-if="filteredEntities.length === 0" class="gr__empty" role="status">
            {{ t('views.graphLibrary.reader.list.empty') }}
          </p>
          <ul v-else class="gr__list" :aria-label="t('views.graphLibrary.reader.list.title')">
            <li v-for="entity in listedEntities" :key="entity.id">
              <button
                type="button"
                class="gr__item"
                :class="{ 'gr__item--on': entity.id === selectedEntityId }"
                :aria-current="entity.id === selectedEntityId ? 'true' : undefined"
                :data-entity-id="entity.id"
                @click="selectEntity(entity.id)"
              >
                <span aria-hidden="true" class="gr__mark">{{ entity.id === selectedEntityId ? '›' : '' }}</span>
                <span aria-hidden="true" class="gr__glyph">{{ glyphByType.get(entity.type) }}</span>
                <span class="gr__itemname">{{ entity.name }}</span>
                <GraphOriginMark v-if="originOf(entity.raw)" :origin="originOf(entity.raw)" />
              </button>
            </li>
          </ul>
          <p v-if="filteredEntities.length > LIST_CAP" class="gr__empty" role="status">
            {{ t('views.graphLibrary.reader.list.capped', { shown: LIST_CAP, total: filteredEntities.length }) }}
          </p>
        </div>
      </div>

      <div class="gr__mid">
        <div class="gr__bar">
          <div class="gr__seg" role="group" :aria-label="t('views.graphLibrary.reader.view.label')">
            <button
              v-for="option in viewOptions"
              :key="option"
              type="button"
              class="gr__segbtn"
              :aria-pressed="view === option"
              :data-view="option"
              @click="view = option"
            >
              {{ t(`views.graphLibrary.reader.view.${option}`) }}
            </button>
          </div>
        </div>

        <div v-if="view === 'net'" class="gr__net" data-testid="gr-net">
          <GraphCanvas
            ref="canvasRef"
            :graph-data="netData"
            :entity-types="netTypes"
            :hide-detail="true"
            @select="onNetSelect"
          />
          <p class="gr__hint">{{ t('views.graphLibrary.reader.net.hint') }}</p>
        </div>
        <GraphReaderTable
          v-else
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

      <GraphReaderDetail
        class="gr__right"
        :entity="selectedEntity"
        :relation="selectedRelation"
        :entity-relations="entityRelations"
        :types="model.types"
        @select-entity="(id: string) => selectEntity(id)"
        @select-edge="(id: string) => selectEdge(id)"
      />
    </div>
  </section>
</template>

<style scoped>
.gr {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  color: var(--fg);
}

.gr__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.gr__counts {
  margin: 0;
  color: var(--fg2);
  font-size: 13.5px;
  font-variant-numeric: tabular-nums;
}

.gr__spacer {
  flex: 1;
}

.gr__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.gr__btn {
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.gr__btn:hover:not(:disabled) {
  background: var(--s4);
}

.gr__btn:disabled {
  cursor: progress;
  color: var(--fg2);
}

.gr__notice {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font-size: 13px;
}

.gr__notice--warn {
  background: var(--warn-soft);
  color: var(--warn);
}

.gr__notice--err {
  background: var(--err-soft);
  color: var(--err);
}

.gr__grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(260px, 340px);
  gap: 16px;
  align-items: start;
}

@media (max-width: 1023px) {
  .gr__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .gr__mid {
    order: -1;
  }
}

.gr__left,
.gr__mid {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.gr__search {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gr__label {
  color: var(--fg2);
  font-size: 12.5px;
  font-weight: 600;
}

.gr__label--h {
  display: flex;
  gap: 8px;
  margin: 0;
}

.gr__input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
}

.gr__input:focus-visible,
.gr__btn:focus-visible,
.gr__type:focus-visible,
.gr__item:focus-visible,
.gr__segbtn:focus-visible,
.gr__link:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.gr__group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gr__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gr__link {
  border: none;
  background: transparent;
  color: var(--acc-text);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  padding: 2px 4px;
}

.gr__types,
.gr__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.gr__list {
  max-height: 360px;
  overflow: auto;
}

.gr__type,
.gr__item {
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

.gr__type:hover,
.gr__item:hover {
  background: var(--s3);
}

.gr__type[aria-pressed='true'],
.gr__item--on {
  background: var(--acc-soft);
  font-weight: 650;
}

.gr__check,
.gr__mark {
  display: inline-block;
  width: 1em;
  color: var(--acc-text);
  font-weight: 700;
}

.gr__glyph {
  color: var(--fg2);
}

.gr__typename,
.gr__itemname {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.gr__num {
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
  font-weight: 400;
}

.gr__empty {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}

.gr__bar {
  display: flex;
  align-items: center;
}

.gr__seg {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
}

.gr__segbtn {
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

.gr__segbtn[aria-pressed='true'] {
  background: var(--s2);
  color: var(--fg);
  box-shadow: inset 0 -2px 0 var(--acc);
}

.gr__net {
  position: relative;
  height: clamp(360px, 60vh, 720px);
  border-radius: var(--ag-r-12);
  background: var(--s2);
  overflow: hidden;
}

.gr__hint {
  position: absolute;
  left: 12px;
  bottom: 8px;
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
  pointer-events: none;
}
</style>
