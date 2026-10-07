<script setup lang="ts">
/**
 * Detailspalte des Graph-Lesers (#1797): gewaehlte Entitaet (Name, Typ, Aliase,
 * Beschreibung, Beziehungen, Herkunft) oder gewaehlte Beziehung. Zeigt nur, was
 * die Graphdaten tragen: ein Dokument- oder Abschnittsname steht nicht an Knoten
 * und Kanten, nur die Zahl der Quellenfragmente (`episode_ids`).
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ReaderEntity, ReaderRelation, ReaderType } from '@/composables/graph-library/graphReaderModel'

const ATTRIBUTE_CAP = 12

const props = defineProps<{
  entity: ReaderEntity | null
  relation: ReaderRelation | null
  /** Beziehungen der gewaehlten Entitaet. */
  entityRelations: readonly ReaderRelation[]
  types: readonly ReaderType[]
}>()

const emit = defineEmits<{
  'select-entity': [id: string]
  'select-edge': [id: string]
}>()

const { t } = useI18n()

const glyph = computed(() => props.types.find((type) => type.name === props.entity?.type)?.glyph ?? '')

/** Verschiedene Quellenfragmente ueber alle Beziehungen der Entitaet. */
const entityEpisodeCount = computed(() => {
  const ids = new Set<string>()
  for (const relation of props.entityRelations) {
    for (const id of relation.raw.episode_ids ?? []) ids.add(String(id))
  }
  return ids.size
})

const attributes = computed(() => {
  const attrs = props.entity?.raw.attributes ?? {}
  const rows: Array<{ key: string; value: string }> = []
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'aliases' || key === 'alias') continue
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      if (String(value) !== '') rows.push({ key, value: String(value) })
    }
  }
  return rows.slice(0, ATTRIBUTE_CAP)
})
</script>

<template>
  <aside class="grd" :aria-label="t('views.graphLibrary.reader.detail.label')">
    <p v-if="!entity && !relation" class="grd__hint">{{ t('views.graphLibrary.reader.detail.none') }}</p>

    <template v-else-if="entity">
      <header class="grd__head">
        <h2 class="grd__name">{{ entity.name }}</h2>
        <span class="grd__type"><span aria-hidden="true">{{ glyph }}</span> {{ entity.type }}</span>
      </header>

      <section v-if="entity.aliases.length" class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.aliases') }}</h3>
        <p class="grd__p">{{ entity.aliases.join(', ') }}</p>
      </section>

      <section v-if="entity.summary" class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.description') }}</h3>
        <p class="grd__p">{{ entity.summary }}</p>
      </section>

      <section v-if="attributes.length" class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.attributes') }}</h3>
        <dl class="grd__dl">
          <template v-for="row in attributes" :key="row.key">
            <dt>{{ row.key }}</dt>
            <dd>{{ row.value }}</dd>
          </template>
        </dl>
      </section>

      <section class="grd__sec">
        <h3 class="grd__h">
          {{ t('views.graphLibrary.reader.detail.relations', { n: entityRelations.length }) }}
        </h3>
        <p v-if="entityRelations.length === 0" class="grd__p grd__p--quiet">
          {{ t('views.graphLibrary.reader.detail.noRelations') }}
        </p>
        <ul v-else class="grd__list">
          <li v-for="rel in entityRelations" :key="rel.id">
            <button type="button" class="grd__link" @click="emit('select-edge', rel.id)">
              <span aria-hidden="true">{{ rel.fromId === entity.id ? '→' : '←' }}</span>
              <span class="grd__sr">
                {{ t(rel.fromId === entity.id ? 'views.graphLibrary.reader.detail.outgoing' : 'views.graphLibrary.reader.detail.incoming') }}
              </span>
              {{ rel.fromId === entity.id ? rel.toName : rel.fromName }}
              <span class="grd__rel">{{ rel.label }}</span>
            </button>
          </li>
        </ul>
      </section>

      <section class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.origin') }}</h3>
        <p class="grd__p">{{ t('views.graphLibrary.reader.detail.episodes', { n: entityEpisodeCount }) }}</p>
        <p v-if="entity.createdAt" class="grd__p grd__p--quiet">
          {{ t('views.graphLibrary.reader.detail.created', { date: entity.createdAt }) }}
        </p>
        <p class="grd__p grd__p--quiet">{{ t('views.graphLibrary.reader.detail.noDocument') }}</p>
      </section>
    </template>

    <template v-else-if="relation">
      <header class="grd__head">
        <h2 class="grd__name">{{ relation.label || t('views.graphLibrary.reader.detail.unnamedRelation') }}</h2>
        <span class="grd__type">{{ t('views.graphLibrary.reader.detail.relationKind') }}</span>
      </header>

      <section class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.between') }}</h3>
        <ul class="grd__list">
          <li>
            <button type="button" class="grd__link" @click="emit('select-entity', relation.fromId)">
              <span class="grd__rel">{{ t('views.graphLibrary.reader.detail.from') }}</span>
              {{ relation.fromName }}
            </button>
          </li>
          <li>
            <button type="button" class="grd__link" @click="emit('select-entity', relation.toId)">
              <span class="grd__rel">{{ t('views.graphLibrary.reader.detail.to') }}</span>
              {{ relation.toName }}
            </button>
          </li>
        </ul>
      </section>

      <section v-if="relation.fact" class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.fact') }}</h3>
        <p class="grd__p">{{ relation.fact }}</p>
      </section>

      <section class="grd__sec">
        <h3 class="grd__h">{{ t('views.graphLibrary.reader.detail.origin') }}</h3>
        <p class="grd__p">{{ t('views.graphLibrary.reader.detail.episodes', { n: relation.episodeCount }) }}</p>
        <p v-if="relation.createdAt" class="grd__p grd__p--quiet">
          {{ t('views.graphLibrary.reader.detail.created', { date: relation.createdAt }) }}
        </p>
        <p class="grd__p grd__p--quiet">{{ t('views.graphLibrary.reader.detail.noDocument') }}</p>
      </section>
    </template>
  </aside>
</template>

<style scoped>
.grd {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
  padding: 16px 18px;
  background: var(--s2);
  border-radius: var(--ag-r-12);
  color: var(--fg);
  overflow-wrap: anywhere;
}

.grd__hint {
  margin: 0;
  color: var(--fg2);
  font-size: 13.5px;
  line-height: 1.5;
}

.grd__head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.grd__name {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  line-height: 1.35;
}

.grd__type {
  align-self: flex-start;
  padding: 2px 10px;
  border-radius: var(--ag-r-pill);
  background: var(--s3);
  color: var(--fg2);
  font-size: 12px;
  font-weight: 600;
}

.grd__sec {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.grd__h {
  margin: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--fg2);
}

.grd__p {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.5;
}

.grd__p--quiet {
  color: var(--fg2);
  font-size: 12.5px;
}

.grd__dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 12px;
  margin: 0;
  font-size: 13px;
}

.grd__dl dt {
  color: var(--fg2);
}

.grd__dl dd {
  margin: 0;
}

.grd__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.grd__link {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: var(--ag-r-6);
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  text-align: left;
  cursor: pointer;
}

.grd__link:hover {
  background: var(--s3);
}

.grd__link:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.grd__rel {
  color: var(--fg2);
  font-size: 12.5px;
}

.grd__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
