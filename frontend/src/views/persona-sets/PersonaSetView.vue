<script setup lang="ts">
/**
 * Satz-Ansicht `/persona-sets/:setId` (#1807, Etappe 7, E7-F2): Kopf mit
 * Sperrzustand, Karten mit Herkunftsmarke, Filter, Mehrfachauswahl mit
 * Löschen, Qualitätshinweise und der Editor-Platzhalter. Ändernde Bedienelemente
 * sind bei gesperrtem Satz deaktiviert und nennen den Grund (Ausweg: Duplizieren).
 * Freigeben/Ablehnen fehlt bewusst: der Vertrag trägt kein Freigabefeld.
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PersonaCard from '@/components/persona-sets/PersonaCard.vue'
import PersonaEditorDialog from '@/components/persona-sets/PersonaEditorDialog.vue'
import PersonaSetDraftPanel from '@/components/persona-sets/PersonaSetDraftPanel.vue'
import PersonaSetFilters from '@/components/persona-sets/PersonaSetFilters.vue'
import PersonaSetHeader from '@/components/persona-sets/PersonaSetHeader.vue'
import PersonaSetQualitySummary from '@/components/persona-sets/PersonaSetQualitySummary.vue'
import { PersonaSetDetailTestId as Id } from '@/components/persona-sets/detailTestIds'
import { duplicatePersonaSet } from '@/api/personaSets'
import { usePersonaSet } from '@/composables/personaSets/usePersonaSet'
import { usePersonaSetFilters } from '@/composables/personaSets/usePersonaSetFilters'
import { describeError } from '@/composables/run/simulation/simulationEnvelope'
import type { PersonaSetEntry, PersonaSetProfileInput, PersonaSetQualityIssue } from '@/contracts/personaSetContract'
import { PersonaSetTestId } from '@/contracts/testIds'

const props = defineProps<{ setId: string }>()
const { t } = useI18n()
const router = useRouter()
const {
  record, loading, error, notFound, isLocked, entries, actionError, conflictError, busy,
  quality, qualityLoading, qualityError,
  draftExample, drafting, draftProviderError,
  load, loadQuality, draft, clearDraftExample,
  addEntry, updateEntry, deleteEntries, updateMeta,
} = usePersonaSet(() => props.setId)
const filters = usePersonaSetFilters(entries)

const selected = ref<Set<string>>(new Set())
const confirmingDelete = ref(false)
const editorOpen = ref(false)
const editingEntry = ref<PersonaSetEntry | null>(null)
const announcement = ref('')
const duplicateError = ref<string | null>(null)
const duplicating = ref(false)
const deleteButton = ref<HTMLButtonElement | null>(null)
const addButton = ref<HTMLButtonElement | null>(null)

const issuesByEntry = computed(() => {
  const map = new Map<string, readonly PersonaSetQualityIssue[]>()
  for (const p of quality.value?.personas ?? []) if (p.issues.length > 0) map.set(p.entry_id, p.issues)
  return map
})
const selectedCount = computed(() => selected.value.size)
const allShownSelected = computed(
  () => filters.filtered.value.length > 0 && filters.filtered.value.every((e) => selected.value.has(e.entry_id)),
)
const mutationBlocked = computed(() => isLocked.value || busy.value)

async function init(): Promise<void> {
  selected.value = new Set()
  confirmingDelete.value = false
  await load()
  if (record.value) void loadQuality()
}

onMounted(() => void init())
watch(() => props.setId, () => void init())
watch(
  () => [filters.filtered.value.length, entries.value.length] as const,
  ([shown, total]) => {
    announcement.value = t('views.personaSets.detail.filter.count', { shown, total })
  },
)
watch(entries, (list) => {
  const ids = new Set(list.map((e) => e.entry_id))
  selected.value = new Set([...selected.value].filter((id) => ids.has(id)))
})

function toggle(entryId: string): void {
  const next = new Set(selected.value)
  if (next.has(entryId)) next.delete(entryId)
  else next.add(entryId)
  selected.value = next
  confirmingDelete.value = false
}

function toggleAll(): void {
  selected.value = allShownSelected.value ? new Set() : new Set(filters.filtered.value.map((e) => e.entry_id))
  confirmingDelete.value = false
}

async function confirmDelete(): Promise<void> {
  const ids = [...selected.value]
  const ok = await deleteEntries(ids)
  confirmingDelete.value = false
  if (ok) {
    selected.value = new Set()
    announcement.value = t('views.personaSets.detail.announce.deleted', { n: ids.length })
    void loadQuality()
  }
  await nextTick()
  // Nach erfolgreichem Löschen ist die Auswahl leer und der Löschknopf deaktiviert;
  // ein deaktivierter Knopf nimmt keinen Fokus an, der Fokus fiele auf <body>.
  const target = deleteButton.value?.disabled ? addButton.value : deleteButton.value
  target?.focus()
}

function openNew(): void {
  editingEntry.value = null
  editorOpen.value = true
}

function openEntry(entryId: string): void {
  editingEntry.value = entries.value.find((e) => e.entry_id === entryId) ?? null
  editorOpen.value = editingEntry.value !== null
}

async function save(profile: PersonaSetProfileInput): Promise<void> {
  const existing = editingEntry.value
  const saved = existing
    ? await updateEntry(existing.entry_id, { profile })
    : await addEntry({ origin: 'manual', profile })
  if (saved) {
    editorOpen.value = false
    announcement.value = t('views.personaSets.detail.announce.saved', { name: saved.profile.name })
    void loadQuality()
  }
}

async function rename(payload: { name: string; description: string }): Promise<void> {
  if (await updateMeta(payload)) announcement.value = t('views.personaSets.detail.announce.renamed')
}

async function duplicate(): Promise<void> {
  if (!record.value || duplicating.value) return
  duplicating.value = true
  duplicateError.value = null
  try {
    const name = t('views.personaSets.detail.header.duplicateName', { name: record.value.name }).slice(0, 120)
    const copy = await duplicatePersonaSet(props.setId, { name })
    await router.push({ name: 'PersonaSet', params: { setId: copy.id } })
  } catch (err) {
    duplicateError.value = describeError(err)
  } finally {
    duplicating.value = false
  }
}
</script>

<template>
  <div :data-testid="PersonaSetTestId.detailRoot">
    <PageHeader :title="record?.name ?? t('views.personaSets.detail.title')" />
    <div class="sr-only" role="status" aria-live="polite" :data-testid="Id.live">{{ announcement }}</div>

    <p v-if="loading" role="status" aria-busy="true" :data-testid="PersonaSetTestId.loading">
      {{ t('views.personaSets.loading') }}
    </p>

    <div v-else-if="notFound" role="alert" :data-testid="Id.notFound">
      <p>{{ t('views.personaSets.detail.notFound') }}</p>
      <RouterLink :to="{ name: 'LibraryPersonaSets' }">{{ t('views.personaSets.detail.backToLibrary') }}</RouterLink>
    </div>

    <div v-else-if="error" role="alert" :data-testid="PersonaSetTestId.error">
      <p>{{ error }}</p>
      <button type="button" :data-testid="Id.retry" @click="init">{{ t('views.personaSets.retry') }}</button>
    </div>

    <template v-else-if="record">
      <PersonaSetHeader
        :record="record"
        :locked="isLocked"
        :busy="busy || duplicating"
        :duplicate-error="duplicateError"
        @rename="rename"
        @duplicate="duplicate"
      />

      <p v-if="conflictError" role="alert" :data-testid="Id.conflictError">{{ t('views.personaSets.detail.conflict') }} {{ actionError }}</p>
      <p v-else-if="actionError" role="alert" :data-testid="Id.actionError">{{ actionError }}</p>

      <PersonaSetQualitySummary :report="quality" :loading="qualityLoading" :error="qualityError" @retry="loadQuality" />

      <PersonaSetDraftPanel
        :drafting="drafting"
        :provider-error="draftProviderError"
        :action-error="draftProviderError ? null : actionError"
        :example="draftExample"
        :locked="isLocked"
        @draft="draft"
        @dismiss="clearDraftExample"
      />

      <p v-if="entries.length === 0" :data-testid="PersonaSetTestId.empty">
        {{ t('views.personaSets.detail.empty') }}
      </p>

      <template v-else>
        <PersonaSetFilters
          v-model:origin="filters.origin.value"
          v-model:kind="filters.kind.value"
          v-model:role="filters.role.value"
          v-model:query="filters.query.value"
          :origin-options="filters.originOptions.value"
          :kind-options="filters.kindOptions.value"
          :role-options="filters.roleOptions.value"
          :shown="filters.filtered.value.length"
          :total="entries.length"
          :is-filtered="filters.isFiltered.value"
          @reset="filters.reset"
        />
      </template>

      <div class="pset__toolbar" role="toolbar" :aria-label="t('views.personaSets.detail.toolbar.label')">
        <button ref="addButton" type="button" :disabled="mutationBlocked" :aria-describedby="isLocked ? Id.lockedReason : undefined" :data-testid="Id.add" @click="openNew">
          {{ t('views.personaSets.detail.toolbar.add') }}
        </button>
        <label v-if="entries.length > 0">
          <input type="checkbox" :checked="allShownSelected" :disabled="isLocked" :data-testid="Id.selectAll" @change="toggleAll" />
          {{ t('views.personaSets.detail.toolbar.selectAll') }}
        </label>
        <button
          ref="deleteButton"
          type="button"
          :disabled="mutationBlocked || selectedCount === 0"
          :aria-describedby="isLocked ? Id.lockedReason : undefined"
          :data-testid="Id.deleteSelected"
          @click="confirmingDelete = true"
        >
          {{ t('views.personaSets.detail.toolbar.deleteSelected', { n: selectedCount }) }}
        </button>
        <span v-if="isLocked" :id="Id.lockedReason" class="pset__reason" :data-testid="Id.lockedReason">
          {{ t('views.personaSets.detail.toolbar.lockedReason') }}
        </span>
      </div>

      <div v-if="confirmingDelete" role="alertdialog" :aria-label="t('views.personaSets.detail.confirm.label')" :data-testid="Id.deleteConfirm">
        <p>{{ t('views.personaSets.detail.confirm.text', { n: selectedCount }) }}</p>
        <button type="button" :disabled="busy" :data-testid="Id.deleteConfirmYes" @click="confirmDelete">
          {{ t('views.personaSets.detail.confirm.yes') }}
        </button>
        <button type="button" :data-testid="Id.deleteConfirmNo" @click="confirmingDelete = false">
          {{ t('views.personaSets.detail.confirm.no') }}
        </button>
      </div>

      <p v-if="entries.length > 0 && filters.filtered.value.length === 0" :data-testid="Id.noMatches">
        {{ t('views.personaSets.detail.filter.noMatches') }}
      </p>
      <ul v-else class="pset__cards" :data-testid="Id.cards" :aria-label="t('views.personaSets.detail.cards.label')">
        <PersonaCard
          v-for="entry in filters.filtered.value"
          :key="entry.entry_id"
          :entry="entry"
          :selected="selected.has(entry.entry_id)"
          :select-disabled="isLocked"
          :issues="issuesByEntry.get(entry.entry_id) ?? []"
          @toggle="toggle"
          @open="openEntry"
        />
      </ul>

      <PersonaEditorDialog
        v-model:open="editorOpen"
        :entry="editingEntry"
        :locked="isLocked"
        :busy="busy"
        :error="actionError"
        @save="save"
      />
    </template>
  </div>
</template>

<style scoped>
.pset__toolbar { display: flex; flex-wrap: wrap; gap: var(--sp-3, 12px); align-items: center; margin-bottom: var(--sp-4, 16px); }
.pset__reason { color: var(--text-secondary, var(--fg-muted)); font-size: var(--fs-caption-1, 12px); }
.pset__cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--sp-4, 16px);
  padding: 0;
  margin: 0;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
