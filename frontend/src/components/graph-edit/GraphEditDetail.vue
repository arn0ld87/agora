<script setup lang="ts">
/**
 * Bearbeitungsspalte des Graphen (#1808, Etappe 8).
 *
 * Eine Spalte, vier Modi: Ansehen der Auswahl, Entität anlegen, Beziehung
 * anlegen und Zusammenführen. Abgeschickt wird nur, was sich geändert hat —
 * der Vertrag lehnt ein leeres Feld-Objekt ab, und ein unberührtes Feld soll
 * keine Embedding-Neuberechnung ausloesen.
 *
 * `editable` false heißt gesperrt: dann zeigt die Spalte nur noch, was
 * vorhanden ist, und nennt den Grund. Kein deaktivierter Knopf allein — der
 * Sperrzustand steht als Band darueber (`GraphLockBanner`).
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { GraphEditTestId } from '@/contracts/testIds'
import type { EntityUpdateInput, RelationUpdateInput } from '@/contracts/graphEditContract'
import type { ReaderEntity, ReaderRelation } from '@/composables/graph-library/graphReaderModel'
import GraphOriginMark from './GraphOriginMark.vue'
import { originOf } from './graphOrigin'

export type EditMode = 'view' | 'create-entity' | 'create-relation' | 'merge'

const props = defineProps<{
  entity: ReaderEntity | null
  relation: ReaderRelation | null
  entities: readonly ReaderEntity[]
  relations: readonly ReaderRelation[]
  ontologyTypes?: readonly string[]
  editable: boolean
  busy: boolean
  mode: EditMode
}>()

const emit = defineEmits<{
  'update-entity': [uuid: string, patch: EntityUpdateInput]
  'create-entity': [args: { name: string; entity_type: string; summary?: string; aliases: string[] }]
  'delete-entity': [uuid: string]
  'update-relation': [uuid: string, patch: RelationUpdateInput]
  'create-relation': [args: { source_uuid: string; target_uuid: string; name: string; fact: string }]
  'delete-relation': [uuid: string]
  'merge': [args: { target_uuid: string; source_uuids: string[] }]
  'mode': [mode: EditMode]
}>()

const { t } = useI18n()

const NO_VALUE = '—'

// --- Entität ---------------------------------------------------------------

const name = ref('')
const entityType = ref('')
const summary = ref('')
const aliases = ref('')
const confirmingEntityDelete = ref(false)

const typeOptions = computed(() => {
  const seen: string[] = []
  if (props.ontologyTypes) {
    for (const t of props.ontologyTypes) if (t && !seen.includes(t)) seen.push(t)
  }
  for (const entity of props.entities) if (entity.type && !seen.includes(entity.type)) seen.push(entity.type)
  return seen
})

/** Die Felder der Auswahl in die Formularfelder spiegeln. */
watch(
  () => [props.entity?.id, props.mode] as const,
  () => {
    const entity = props.entity
    name.value = entity?.name ?? ''
    entityType.value = entity?.type ?? ''
    summary.value = entity?.summary ?? ''
    aliases.value = entity?.aliases.join(', ') ?? ''
    confirmingEntityDelete.value = false
  },
  { immediate: true },
)

function aliasList(raw: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const part of raw.split(',')) {
    const value = part.trim()
    // Leere Stuecke und Doppelungen raus: der Vertrag dedupliziert auch, aber
    // die Form soll zeigen, was tatsaechlich gespeichert wuerde.
    const key = value.toLocaleLowerCase('de')
    if (value && !seen.has(key)) {
      seen.add(key)
      out.push(value)
    }
  }
  return out
}

/** Zwei Alias-Listen gelten als gleich, wenn Laenge und Reihenfolge stimmen. */
function sameAliases(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index])
}

const entityCanSubmit = computed(() => name.value.trim() !== '' && entityType.value !== NO_VALUE && entityType.value !== '')

function submitEntity(): void {
  if (!props.entity || !entityCanSubmit.value) return
  const patch: EntityUpdateInput = {}
  if (name.value.trim() !== props.entity.name) patch.name = name.value.trim()
  if (entityType.value !== props.entity.type) patch.entity_type = entityType.value
  if (summary.value !== props.entity.summary) patch.summary = summary.value
  const list = aliasList(aliases.value)
  if (!sameAliases(list, props.entity.aliases)) patch.aliases = list
  if (Object.keys(patch).length === 0) return
  emit('update-entity', props.entity.id, patch)
}

function submitCreateEntity(): void {
  if (!entityCanSubmit.value) return
  const args: { name: string; entity_type: string; summary?: string; aliases: string[] } = {
    name: name.value.trim(),
    entity_type: entityType.value,
    aliases: aliasList(aliases.value),
  }
  // Leere Beschreibung weglassen statt sie mitzuschicken: das Feld hat im
  // Vertrag einen Default, ein leerer String waere ein eigener Wert.
  if (summary.value.trim() !== '') args.summary = summary.value.trim()
  emit('create-entity', args)
}

function confirmEntityDelete(): void {
  if (!props.entity) return
  emit('delete-entity', props.entity.id)
}

// --- Beziehung -------------------------------------------------------------

const sourceUuid = ref('')
const targetUuid = ref('')
const relationName = ref('')
const relationFact = ref('')
const confirmingRelationDelete = ref(false)

const relationCanSubmit = computed(
  () =>
    sourceUuid.value !== '' &&
    targetUuid.value !== '' &&
    sourceUuid.value !== targetUuid.value &&
    relationName.value.trim() !== '' &&
    relationFact.value.trim() !== '',
)

watch(
  () => [props.relation?.id, props.mode] as const,
  () => {
    const relation = props.relation
    sourceUuid.value = relation?.fromId ?? ''
    targetUuid.value = relation?.toId ?? ''
    relationName.value = relation?.label ?? ''
    relationFact.value = relation?.fact ?? ''
    confirmingRelationDelete.value = false
  },
  { immediate: true },
)

function submitRelation(): void {
  if (!props.relation || !relationCanSubmit.value) return
  const patch: RelationUpdateInput = {}
  if (relationName.value.trim() !== props.relation.label) patch.name = relationName.value.trim()
  if (relationFact.value.trim() !== props.relation.fact) patch.fact = relationFact.value.trim()
  if (Object.keys(patch).length === 0) return
  emit('update-relation', props.relation.id, patch)
}

function submitCreateRelation(): void {
  if (!relationCanSubmit.value) return
  emit('create-relation', {
    source_uuid: sourceUuid.value,
    target_uuid: targetUuid.value,
    name: relationName.value.trim(),
    fact: relationFact.value.trim(),
  })
}

function confirmRelationDelete(): void {
  if (!props.relation) return
  emit('delete-relation', props.relation.id)
}

// --- Zusammenführen --------------------------------------------------------

const mergeSources = ref<string[]>([])

watch(
  () => [props.entity?.id, props.mode] as const,
  () => {
    mergeSources.value = []
  },
)

const mergeCandidates = computed(() => props.entities.filter((entity) => entity.id !== props.entity?.id))

function toggleMergeSource(id: string, checked: boolean): void {
  const next = new Set(mergeSources.value)
  if (checked) next.add(id)
  else next.delete(id)
  mergeSources.value = [...next]
}

function submitMerge(): void {
  if (!props.entity || mergeSources.value.length === 0) return
  emit('merge', { target_uuid: props.entity.id, source_uuids: mergeSources.value })
}

const entityOrigin = computed(() => originOf(props.entity?.raw))
const relationOrigin = computed(() => originOf(props.relation?.raw))
const entityChangedAt = computed(() => {
  const provenance = (props.entity?.raw as { provenance?: { changed_at?: string | null } } | undefined)?.provenance
  return provenance?.changed_at ?? null
})
const relationChangedAt = computed(() => {
  const provenance = (props.relation?.raw as { provenance?: { changed_at?: string | null } } | undefined)?.provenance
  return provenance?.changed_at ?? null
})

function nameOf(id: string): string {
  return props.entities.find((entity) => entity.id === id)?.name ?? id
}
</script>

<template>
  <aside class="ged" :aria-label="t('views.graphEdit.view.label')">
    <p v-if="!editable" class="ged__locked" data-testid="graph-edit-detail-readonly" role="status">
      {{ t('views.graphEdit.view.notEditable') }}
    </p>

    <!-- Anlegen: Entität -->
    <section v-if="mode === 'create-entity'" class="ged__sec">
      <h2 class="ged__h">{{ t('views.graphEdit.view.entity.createTitle') }}</h2>
      <form class="ged__form" :data-testid="GraphEditTestId.entityForm" @submit.prevent="submitCreateEntity">
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.entity.name') }}</span>
          <input
            v-model="name"
            type="text"
            class="ged__input"
            :data-testid="GraphEditTestId.entityName"
            :disabled="busy"
          />
        </label>
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.entity.type') }}</span>
          <select
            v-model="entityType"
            class="ged__input"
            :data-testid="GraphEditTestId.entityType"
            :disabled="busy"
          >
            <option :value="NO_VALUE">{{ NO_VALUE }}</option>
            <option v-for="option in typeOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </label>
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.entity.aliases') }}</span>
          <input
            v-model="aliases"
            type="text"
            class="ged__input"
            :data-testid="GraphEditTestId.entityAliases"
            :disabled="busy"
          />
        </label>
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.entity.summary') }}</span>
          <textarea
            v-model="summary"
            class="ged__input ged__input--area"
            rows="3"
            :data-testid="GraphEditTestId.entitySummary"
            :disabled="busy"
          />
        </label>
        <div class="ged__actions">
          <button
            type="submit"
            class="ged__btn ged__btn--primary"
            :data-testid="GraphEditTestId.entitySubmit"
            :disabled="!entityCanSubmit || busy"
          >
            {{ t('views.graphEdit.view.entity.submitCreate') }}
          </button>
          <button
            type="button"
            class="ged__btn"
            :data-testid="GraphEditTestId.entityCancel"
            :disabled="busy"
            @click="emit('mode', 'view')"
          >
            {{ t('views.graphEdit.view.entity.cancel') }}
          </button>
        </div>
      </form>
    </section>

    <!-- Anlegen: Beziehung -->
    <section v-else-if="mode === 'create-relation'" class="ged__sec">
      <h2 class="ged__h">{{ t('views.graphEdit.view.relation.createTitle') }}</h2>
      <form class="ged__form" :data-testid="GraphEditTestId.relationForm" @submit.prevent="submitCreateRelation">
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.relation.source') }}</span>
          <select
            v-model="sourceUuid"
            class="ged__input"
            :data-testid="GraphEditTestId.relationSource"
            :disabled="busy"
          >
            <option value="">{{ NO_VALUE }}</option>
            <option v-for="option in entities" :key="option.id" :value="option.id">{{ option.name }}</option>
          </select>
        </label>
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.relation.target') }}</span>
          <select
            v-model="targetUuid"
            class="ged__input"
            :data-testid="GraphEditTestId.relationTarget"
            :disabled="busy"
          >
            <option value="">{{ NO_VALUE }}</option>
            <option v-for="option in entities" :key="option.id" :value="option.id">{{ option.name }}</option>
          </select>
        </label>
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.relation.name') }}</span>
          <input
            v-model="relationName"
            type="text"
            class="ged__input"
            :data-testid="GraphEditTestId.relationName"
            :disabled="busy"
          />
        </label>
        <label class="ged__field">
          <span class="ged__label">{{ t('views.graphEdit.view.relation.fact') }}</span>
          <textarea
            v-model="relationFact"
            class="ged__input ged__input--area"
            rows="3"
            :data-testid="GraphEditTestId.relationFact"
            :disabled="busy"
          />
        </label>
        <div class="ged__actions">
          <button
            type="submit"
            class="ged__btn ged__btn--primary"
            :data-testid="GraphEditTestId.relationSubmit"
            :disabled="!relationCanSubmit || busy"
          >
            {{ t('views.graphEdit.view.relation.submitCreate') }}
          </button>
          <button
            type="button"
            class="ged__btn"
            :data-testid="GraphEditTestId.relationCancel"
            :disabled="busy"
            @click="emit('mode', 'view')"
          >
            {{ t('views.graphEdit.view.relation.cancel') }}
          </button>
        </div>
      </form>
    </section>

    <!-- Zusammenführen -->
    <section v-else-if="mode === 'merge' && entity" class="ged__sec" :data-testid="GraphEditTestId.mergePanel">
      <h2 class="ged__h">{{ t('views.graphEdit.view.merge.title') }}</h2>
      <p class="ged__p">{{ t('views.graphEdit.view.merge.hint') }}</p>
      <p class="ged__p ged__p--quiet">{{ entity.name }}</p>
      <fieldset class="ged__set">
        <legend class="ged__label">{{ t('views.graphEdit.view.merge.source') }}</legend>
        <label v-for="candidate in mergeCandidates" :key="candidate.id" class="ged__check">
          <input
            type="checkbox"
            :data-testid="GraphEditTestId.mergeSource"
            :data-entity-id="candidate.id"
            :checked="mergeSources.includes(candidate.id)"
            :disabled="busy"
            @change="toggleMergeSource(candidate.id, ($event.target as HTMLInputElement).checked)"
          />
          <span>{{ candidate.name }}</span>
        </label>
      </fieldset>
      <div class="ged__actions">
        <button
          type="button"
          class="ged__btn ged__btn--primary"
          :data-testid="GraphEditTestId.mergeSubmit"
          :disabled="mergeSources.length === 0 || busy"
          @click="submitMerge"
        >
          {{ t('views.graphEdit.view.merge.submit') }}
        </button>
        <button
          type="button"
          class="ged__btn"
          :data-testid="GraphEditTestId.entityCancel"
          :disabled="busy"
          @click="emit('mode', 'view')"
        >
          {{ t('views.graphEdit.view.entity.cancel') }}
        </button>
      </div>
    </section>

    <!-- Auswahl: Entität -->
    <template v-else-if="entity">
      <header class="ged__head">
        <h2 class="ged__name">{{ entity.name }}</h2>
        <GraphOriginMark :origin="entityOrigin" :changed-at="entityChangedAt" />
      </header>

      <template v-if="editable">
        <form class="ged__form" :data-testid="GraphEditTestId.entityForm" @submit.prevent="submitEntity">
          <label class="ged__field">
            <span class="ged__label">{{ t('views.graphEdit.view.entity.name') }}</span>
            <input
              v-model="name"
              type="text"
              class="ged__input"
              :data-testid="GraphEditTestId.entityName"
              :disabled="busy"
            />
          </label>
          <label class="ged__field">
            <span class="ged__label">{{ t('views.graphEdit.view.entity.type') }}</span>
            <select
              v-model="entityType"
              class="ged__input"
              :data-testid="GraphEditTestId.entityType"
              :disabled="busy"
            >
              <option :value="NO_VALUE">{{ NO_VALUE }}</option>
              <option v-for="option in typeOptions" :key="option" :value="option">{{ option }}</option>
            </select>
          </label>
          <label class="ged__field">
            <span class="ged__label">{{ t('views.graphEdit.view.entity.aliases') }}</span>
            <input
              v-model="aliases"
              type="text"
              class="ged__input"
              :data-testid="GraphEditTestId.entityAliases"
              :disabled="busy"
            />
          </label>
          <label class="ged__field">
            <span class="ged__label">{{ t('views.graphEdit.view.entity.summary') }}</span>
            <textarea
              v-model="summary"
              class="ged__input ged__input--area"
              rows="3"
              :data-testid="GraphEditTestId.entitySummary"
              :disabled="busy"
            />
          </label>
          <div class="ged__actions">
            <button
              type="submit"
              class="ged__btn ged__btn--primary"
              :data-testid="GraphEditTestId.entitySubmit"
              :disabled="!entityCanSubmit || busy"
            >
              {{ t('views.graphEdit.view.entity.submitSave') }}
            </button>
            <button
              type="button"
              class="ged__btn"
              :data-testid="GraphEditTestId.mergeOpen"
              :disabled="busy"
              @click="emit('mode', 'merge')"
            >
              {{ t('views.graphEdit.view.merge.open') }}
            </button>
          </div>
        </form>

        <div class="ged__actions">
          <button
            v-if="!confirmingEntityDelete"
            type="button"
            class="ged__btn ged__btn--danger"
            :data-testid="GraphEditTestId.entityDelete"
            :disabled="busy"
            @click="confirmingEntityDelete = true"
          >
            {{ t('views.graphEdit.view.entity.delete') }}
          </button>
          <template v-else>
            <span class="ged__confirm">{{ t('views.graphEdit.view.entity.deleteConfirm') }}</span>
            <button
              type="button"
              class="ged__btn ged__btn--danger"
              :data-testid="GraphEditTestId.entityDeleteConfirm"
              :disabled="busy"
              @click="confirmEntityDelete"
            >
              {{ t('views.graphEdit.view.entity.delete') }}
            </button>
            <button type="button" class="ged__btn" :disabled="busy" @click="confirmingEntityDelete = false">
              {{ t('views.graphEdit.view.entity.cancel') }}
            </button>
          </template>
        </div>
      </template>

      <section v-else class="ged__sec">
        <p v-if="entity.summary" class="ged__p">{{ entity.summary }}</p>
        <p v-if="entity.aliases.length" class="ged__p ged__p--quiet">{{ entity.aliases.join(', ') }}</p>
      </section>
    </template>

    <!-- Auswahl: Beziehung -->
    <template v-else-if="relation">
      <header class="ged__head">
        <h2 class="ged__name">{{ relation.label || relation.fromName }}</h2>
        <GraphOriginMark :origin="relationOrigin" :changed-at="relationChangedAt" />
      </header>
      <p class="ged__p ged__p--quiet">
        {{ nameOf(relation.fromId) }} → {{ nameOf(relation.toId) }}
      </p>

      <template v-if="editable">
        <form class="ged__form" :data-testid="GraphEditTestId.relationForm" @submit.prevent="submitRelation">
          <label class="ged__field">
            <span class="ged__label">{{ t('views.graphEdit.view.relation.name') }}</span>
            <input
              v-model="relationName"
              type="text"
              class="ged__input"
              :data-testid="GraphEditTestId.relationName"
              :disabled="busy"
            />
          </label>
          <label class="ged__field">
            <span class="ged__label">{{ t('views.graphEdit.view.relation.fact') }}</span>
            <textarea
              v-model="relationFact"
              class="ged__input ged__input--area"
              rows="3"
              :data-testid="GraphEditTestId.relationFact"
              :disabled="busy"
            />
          </label>
          <div class="ged__actions">
            <button
              type="submit"
              class="ged__btn ged__btn--primary"
              :data-testid="GraphEditTestId.relationSubmit"
              :disabled="!relationCanSubmit || busy"
            >
              {{ t('views.graphEdit.view.relation.submitSave') }}
            </button>
          </div>
        </form>

        <div class="ged__actions">
          <button
            v-if="!confirmingRelationDelete"
            type="button"
            class="ged__btn ged__btn--danger"
            :data-testid="GraphEditTestId.relationDelete"
            :disabled="busy"
            @click="confirmingRelationDelete = true"
          >
            {{ t('views.graphEdit.view.relation.delete') }}
          </button>
          <template v-else>
            <span class="ged__confirm">{{ t('views.graphEdit.view.relation.deleteConfirm') }}</span>
            <button
              type="button"
              class="ged__btn ged__btn--danger"
              :data-testid="GraphEditTestId.relationDeleteConfirm"
              :disabled="busy"
              @click="confirmRelationDelete"
            >
              {{ t('views.graphEdit.view.relation.delete') }}
            </button>
            <button type="button" class="ged__btn" :disabled="busy" @click="confirmingRelationDelete = false">
              {{ t('views.graphEdit.view.relation.cancel') }}
            </button>
          </template>
        </div>
      </template>

      <section v-else class="ged__sec">
        <p v-if="relation.fact" class="ged__p">{{ relation.fact }}</p>
      </section>
    </template>

    <p v-else class="ged__hint">{{ t('views.graphEdit.view.entity.selectPrompt') }}</p>
  </aside>
</template>

<style scoped>
.ged {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}

.ged__locked {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 12.5px;
  font-weight: 600;
}

.ged__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.ged__name {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.ged__sec,
.ged__form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ged__h {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
}

.ged__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ged__label {
  color: var(--fg2);
  font-size: 12px;
  font-weight: 600;
}

.ged__input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
}

.ged__input--area {
  resize: vertical;
}

.ged__input:focus-visible,
.ged__btn:focus-visible,
.ged__check input:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.ged__set {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  max-height: 220px;
  overflow: auto;
}

.ged__check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.ged__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.ged__btn {
  min-height: 30px;
  padding: 4px 12px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.ged__btn:disabled {
  color: var(--fg2);
  cursor: not-allowed;
}

.ged__btn--primary {
  background: var(--acc);
  color: var(--on-acc);
}

.ged__btn--danger {
  background: var(--err-soft);
  color: var(--err);
}

.ged__confirm {
  color: var(--fg);
  font-size: 12.5px;
}

.ged__p {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}

.ged__p--quiet,
.ged__hint {
  color: var(--fg2);
  font-size: 12.5px;
}
</style>
