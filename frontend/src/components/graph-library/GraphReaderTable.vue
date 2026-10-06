<script setup lang="ts">
/**
 * Tabellen-Ansicht des Graph-Lesers (#1797): zwei Reiter, Entitaeten und
 * Beziehungen, je sortierbar. Echte `th scope`, Auswahl per Taste ueber die
 * Schaltflaeche in der ersten Zelle, gewaehlte Zeile mit Marke und `aria-current`.
 */
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  sortRows,
  type ReaderEntity,
  type ReaderRelation,
  type ReaderType,
  type SortDirection,
} from '@/composables/graph-library/graphReaderModel'

export type TableTab = 'entities' | 'relations'

const ROW_CAP = 500

const props = defineProps<{
  tab: TableTab
  entities: readonly ReaderEntity[]
  relations: readonly ReaderRelation[]
  types: readonly ReaderType[]
  selectedEntityId: string | null
  selectedEdgeId: string | null
}>()

const emit = defineEmits<{
  'update:tab': [tab: TableTab]
  'select-entity': [id: string]
  'select-edge': [id: string]
}>()

const { t } = useI18n()

type EntityColumn = 'name' | 'type' | 'degree' | 'createdAt'
type RelationColumn = 'from' | 'label' | 'to' | 'episodes'

const entitySort = ref<{ column: EntityColumn; direction: SortDirection }>({ column: 'name', direction: 'asc' })
const relationSort = ref<{ column: RelationColumn; direction: SortDirection }>({ column: 'from', direction: 'asc' })

const glyphByType = computed(() => new Map(props.types.map((type) => [type.name, type.glyph])))

const sortedEntities = computed(() => {
  const { column, direction } = entitySort.value
  const key = (row: ReaderEntity): string | number =>
    column === 'degree' ? row.degree : column === 'createdAt' ? (row.createdAt ?? '') : row[column]
  return sortRows(props.entities, key, direction)
})

const sortedRelations = computed(() => {
  const { column, direction } = relationSort.value
  const key = (row: ReaderRelation): string | number =>
    column === 'episodes'
      ? row.episodeCount
      : column === 'from'
        ? row.fromName
        : column === 'to'
          ? row.toName
          : row.label
  return sortRows(props.relations, key, direction)
})

const shownEntities = computed(() => sortedEntities.value.slice(0, ROW_CAP))
const shownRelations = computed(() => sortedRelations.value.slice(0, ROW_CAP))

function toggleEntitySort(column: EntityColumn): void {
  const cur = entitySort.value
  entitySort.value = {
    column,
    direction: cur.column === column && cur.direction === 'asc' ? 'desc' : 'asc',
  }
}

function toggleRelationSort(column: RelationColumn): void {
  const cur = relationSort.value
  relationSort.value = {
    column,
    direction: cur.column === column && cur.direction === 'asc' ? 'desc' : 'asc',
  }
}

function ariaSort(active: boolean, direction: SortDirection): 'ascending' | 'descending' | 'none' {
  if (!active) return 'none'
  return direction === 'asc' ? 'ascending' : 'descending'
}

function arrow(active: boolean, direction: SortDirection): string {
  if (!active) return ''
  return direction === 'asc' ? '▲' : '▼'
}

const tabs: TableTab[] = ['entities', 'relations']
const tabRefs = ref<Record<string, HTMLButtonElement | null>>({})

function onTabKey(event: KeyboardEvent, index: number): void {
  let next = index
  if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = tabs.length - 1
  else return
  event.preventDefault()
  emit('update:tab', tabs[next])
  void nextTick(() => tabRefs.value[tabs[next]]?.focus())
}

const entityColumns: EntityColumn[] = ['name', 'type', 'degree', 'createdAt']
const relationColumns: RelationColumn[] = ['from', 'label', 'to', 'episodes']
</script>

<template>
  <div class="grt">
    <div class="grt__tabs" role="tablist" :aria-label="t('views.graphLibrary.reader.tabs.label')">
      <button
        v-for="(name, index) in tabs"
        :id="`grt-tab-${name}`"
        :key="name"
        :ref="(el) => (tabRefs[name] = el as HTMLButtonElement | null)"
        type="button"
        role="tab"
        class="grt__tab"
        :aria-selected="tab === name"
        :aria-controls="`grt-panel-${name}`"
        :tabindex="tab === name ? 0 : -1"
        @click="emit('update:tab', name)"
        @keydown="onTabKey($event, index)"
      >
        {{ t(`views.graphLibrary.reader.tabs.${name}`) }}
        <span class="grt__count">{{ name === 'entities' ? entities.length : relations.length }}</span>
      </button>
    </div>

    <div
      v-if="tab === 'entities'"
      id="grt-panel-entities"
      role="tabpanel"
      aria-labelledby="grt-tab-entities"
      class="grt__panel"
    >
      <p v-if="entities.length === 0" class="grt__empty" role="status">
        {{ t('views.graphLibrary.reader.table.emptyEntities') }}
      </p>
      <table v-else class="grt__table">
        <caption class="grt__sr">{{ t('views.graphLibrary.reader.table.captionEntities') }}</caption>
        <thead>
          <tr>
            <th
              v-for="column in entityColumns"
              :key="column"
              scope="col"
              :aria-sort="ariaSort(entitySort.column === column, entitySort.direction)"
            >
              <button type="button" class="grt__sort" @click="toggleEntitySort(column)">
                {{ t(`views.graphLibrary.reader.table.entity.${column}`) }}
                <span aria-hidden="true" class="grt__arrow">{{ arrow(entitySort.column === column, entitySort.direction) }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in shownEntities"
            :key="row.id"
            :class="{ 'grt__row--selected': row.id === selectedEntityId }"
            :data-entity-id="row.id"
          >
            <th scope="row" class="grt__rowhead">
              <button
                type="button"
                class="grt__pick"
                :aria-current="row.id === selectedEntityId ? 'true' : undefined"
                @click="emit('select-entity', row.id)"
              >
                <span aria-hidden="true" class="grt__mark">{{ row.id === selectedEntityId ? '›' : '' }}</span>
                {{ row.name }}
              </button>
            </th>
            <td>
              <span aria-hidden="true" class="grt__glyph">{{ glyphByType.get(row.type) }}</span>
              {{ row.type }}
            </td>
            <td class="grt__num">{{ row.degree }}</td>
            <td>{{ row.createdAt ?? '' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="entities.length > ROW_CAP" class="grt__cap" role="status">
        {{ t('views.graphLibrary.reader.table.capped', { shown: ROW_CAP, total: entities.length }) }}
      </p>
    </div>

    <div
      v-else
      id="grt-panel-relations"
      role="tabpanel"
      aria-labelledby="grt-tab-relations"
      class="grt__panel"
    >
      <p v-if="relations.length === 0" class="grt__empty" role="status">
        {{ t('views.graphLibrary.reader.table.emptyRelations') }}
      </p>
      <table v-else class="grt__table">
        <caption class="grt__sr">{{ t('views.graphLibrary.reader.table.captionRelations') }}</caption>
        <thead>
          <tr>
            <th
              v-for="column in relationColumns"
              :key="column"
              scope="col"
              :aria-sort="ariaSort(relationSort.column === column, relationSort.direction)"
            >
              <button type="button" class="grt__sort" @click="toggleRelationSort(column)">
                {{ t(`views.graphLibrary.reader.table.relation.${column}`) }}
                <span aria-hidden="true" class="grt__arrow">{{ arrow(relationSort.column === column, relationSort.direction) }}</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in shownRelations"
            :key="row.id"
            :class="{ 'grt__row--selected': row.id === selectedEdgeId }"
            :data-edge-id="row.id"
          >
            <th scope="row" class="grt__rowhead">
              <button
                type="button"
                class="grt__pick"
                :aria-current="row.id === selectedEdgeId ? 'true' : undefined"
                @click="emit('select-edge', row.id)"
              >
                <span aria-hidden="true" class="grt__mark">{{ row.id === selectedEdgeId ? '›' : '' }}</span>
                {{ row.fromName }}
              </button>
            </th>
            <td>{{ row.label }}</td>
            <td>{{ row.toName }}</td>
            <td class="grt__num">{{ row.episodeCount }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="relations.length > ROW_CAP" class="grt__cap" role="status">
        {{ t('views.graphLibrary.reader.table.capped', { shown: ROW_CAP, total: relations.length }) }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.grt {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.grt__tabs {
  display: flex;
  gap: 4px;
}

.grt__tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 12px;
  border: none;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.grt__tab:hover {
  background: var(--s3);
}

.grt__tab[aria-selected='true'] {
  background: var(--s3);
  color: var(--fg);
  box-shadow: inset 0 -2px 0 var(--acc);
}

.grt__tab:focus-visible,
.grt__sort:focus-visible,
.grt__pick:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.grt__count {
  color: var(--fg3);
  font-variant-numeric: tabular-nums;
}

.grt__panel {
  overflow: auto;
  max-height: clamp(360px, 60vh, 720px);
  background: var(--s2);
  border-radius: var(--ag-r-12);
}

.grt__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  color: var(--fg);
}

.grt__table th,
.grt__table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}

.grt__table thead th {
  position: sticky;
  top: 0;
  background: var(--s2);
  color: var(--fg2);
  font-weight: 600;
  padding: 4px 6px;
  z-index: 1;
}

.grt__rowhead {
  font-weight: 600;
}

.grt__sort,
.grt__pick {
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: inherit;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--ag-r-6);
  text-align: left;
}

.grt__sort:hover,
.grt__pick:hover {
  background: var(--s3);
}

.grt__arrow {
  display: inline-block;
  min-width: 1em;
  font-size: 10px;
  color: var(--acc-text);
}

.grt__mark {
  display: inline-block;
  width: 0.8em;
  color: var(--acc-text);
  font-weight: 700;
}

.grt__row--selected {
  background: var(--acc-soft);
}

.grt__row--selected .grt__pick {
  font-weight: 700;
}

.grt__glyph {
  color: var(--fg2);
  margin-right: 4px;
}

.grt__num {
  font-variant-numeric: tabular-nums;
}

.grt__empty,
.grt__cap {
  margin: 0;
  padding: 16px;
  color: var(--fg2);
  font-size: 13.5px;
}

.grt__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
