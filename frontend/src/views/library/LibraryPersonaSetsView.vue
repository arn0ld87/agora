<script setup lang="ts">
/**
 * Bibliothek → Personasätze (#1807, Etappe 7): Kacheln aller Personasätze mit
 * Suche über den Namen, Anlegen, Duplizieren und Löschen (mit Rückfrage). Daten
 * und Aktionen liefert `usePersonaSets`. Der Sammelsatz „Importiert“ erscheint
 * wie jeder andere Satz. Die Zahl der Sätze geht an die Seitenleiste.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'
import PersonaSetTile from '@/components/persona-sets/library/PersonaSetTile.vue'
import PersonaSetCreateDialog from '@/components/persona-sets/library/PersonaSetCreateDialog.vue'
import PersonaSetRemoveDialog from '@/components/persona-sets/library/PersonaSetRemoveDialog.vue'
import { PersonaSetLibraryTestId as Id } from '@/components/persona-sets/library/libraryTestIds'
import { usePersonaSets } from '@/composables/personaSets/usePersonaSets'
import { useShellBreadcrumbs } from '@/composables/useShellBreadcrumbs'
import { PERSONA_SET_NAME_MAX_LENGTH, type PersonaSetSummary } from '@/contracts/personaSetContract'
import { PersonaSetTestId } from '@/contracts/testIds'
import { useShellStore } from '@/stores/shell'

const { t } = useI18n()
const router = useRouter()
const shell = useShellStore()
const { sets, loading, loaded, error, actionError, lockedError, busy, isEmpty, reload, create, duplicate, remove } =
  usePersonaSets()

const query = ref('')
const createOpen = ref(false)
const removeTarget = ref<PersonaSetSummary | null>(null)
const removeOpen = computed({
  get: () => removeTarget.value !== null,
  set: (open: boolean) => {
    if (!open) removeTarget.value = null
  },
})
/** Meldung für die Live-Region (Erfolg bzw. Sperrhinweis). */
const statusMessage = ref('')

onMounted(() => void reload())

// Die Seitenleiste zeigt die Zahl der Sätze; unbekannt (null) bei Ladefehler, nie 0.
watch(
  [loaded, error, sets],
  () => {
    if (error.value) {
      shell.personaSetCount = null
      shell.personaSetCountFailed = true
    } else if (loaded.value) {
      shell.personaSetCount = sets.value.length
      shell.personaSetCountFailed = false
    }
  },
  { deep: false },
)

const filtered = computed(() => {
  const q = query.value.trim().toLocaleLowerCase()
  return q ? sets.value.filter((s) => s.name.toLocaleLowerCase().includes(q)) : sets.value
})

const noMatches = computed(() => query.value.trim() !== '' && filtered.value.length === 0 && sets.value.length > 0)

const matchesMessage = computed(() =>
  query.value.trim() !== '' && filtered.value.length > 0
    ? t('views.personaSets.library.matches', { n: filtered.value.length, total: sets.value.length })
    : '',
)

const actionMessage = computed(() => {
  if (lockedError.value) return t('views.personaSets.library.messages.locked')
  return actionError.value
    ? t('views.personaSets.library.messages.actionFailed', { error: actionError.value })
    : ''
})

function openSet(id: string): Promise<unknown> {
  return router.push({ name: 'PersonaSet', params: { setId: id } })
}

async function onCreate(value: { name: string; description: string }): Promise<void> {
  statusMessage.value = ''
  const record = await create({ name: value.name, description: value.description })
  if (!record) return
  createOpen.value = false
  statusMessage.value = t('views.personaSets.library.messages.created', { name: record.name })
  await openSet(record.id)
}

async function onDuplicate(set: PersonaSetSummary): Promise<void> {
  statusMessage.value = ''
  const name = t('views.personaSets.library.duplicateName', { name: set.name }).slice(0, PERSONA_SET_NAME_MAX_LENGTH)
  const record = await duplicate(set.id, name)
  if (!record) return
  statusMessage.value = t('views.personaSets.library.messages.duplicated', { name: record.name })
  await openSet(record.id)
}

async function onRemoveConfirm(): Promise<void> {
  const target = removeTarget.value
  if (!target) return
  statusMessage.value = ''
  const removed = await remove(target.id)
  removeTarget.value = null
  if (removed) statusMessage.value = t('views.personaSets.library.messages.deleted', { name: target.name })
}

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: t('views.library.title'), path: '/library/runs' },
  { label: t('views.personaSets.title') },
])
useShellBreadcrumbs(crumbs)
</script>

<template>
  <div class="lps" :data-testid="PersonaSetTestId.libraryRoot">
    <PageHeader :title="t('views.personaSets.title')">
      <template v-if="loaded && !error" #right>
        <span class="lps__count" data-testid="persona-sets-count">{{ sets.length }}</span>
        <button type="button" class="lps__btn lps__btn--primary" :data-testid="Id.newButton" @click="createOpen = true">
          {{ t('views.personaSets.library.new') }}
        </button>
      </template>
    </PageHeader>

    <!-- Live-Region: bleibt im DOM, damit Statusmeldungen vorgelesen werden. -->
    <p class="lps__live" role="status" aria-live="polite" :data-testid="Id.status">
      {{ statusMessage || matchesMessage }}
    </p>

    <div v-if="actionMessage && !createOpen" class="lps__err" role="alert" :data-testid="Id.actionError">
      <p class="lps__text lps__text--fg">{{ actionMessage }}</p>
    </div>

    <p v-if="loading && !loaded" class="lps__text" role="status" aria-busy="true" :data-testid="PersonaSetTestId.loading">
      {{ t('views.personaSets.loading') }}
    </p>

    <div v-else-if="error" class="lps__err" role="alert" :data-testid="PersonaSetTestId.error">
      <p class="lps__errtitle">{{ t('views.personaSets.errorTitle') }}</p>
      <p class="lps__text lps__text--fg">{{ error }}</p>
      <button type="button" class="lps__btn" @click="reload">{{ t('views.personaSets.retry') }}</button>
    </div>

    <div v-else-if="isEmpty" class="lps__empty" :data-testid="PersonaSetTestId.empty">
      <p class="lps__text lps__text--fg">{{ t('views.personaSets.library.empty') }}</p>
      <button type="button" class="lps__btn lps__btn--primary" :data-testid="Id.emptyNew" @click="createOpen = true">
        {{ t('views.personaSets.library.new') }}
      </button>
    </div>

    <template v-else-if="loaded">
      <input
        v-model="query"
        class="lps__search"
        type="search"
        :placeholder="t('views.personaSets.library.searchPlaceholder')"
        :aria-label="t('views.personaSets.library.searchLabel')"
        :data-testid="Id.search"
      />

      <p v-if="noMatches" class="lps__text" :data-testid="Id.noMatches">
        {{ t('views.personaSets.library.noMatches', { query: query.trim() }) }}
      </p>

      <ul v-else class="lps__grid" :aria-label="t('views.personaSets.library.list')" :data-testid="Id.grid">
        <PersonaSetTile
          v-for="set in filtered"
          :key="set.id"
          :set="set"
          :busy="busy"
          @duplicate="onDuplicate"
          @remove="removeTarget = $event"
        />
      </ul>
    </template>

    <PersonaSetCreateDialog v-model="createOpen" :busy="busy" :error="createOpen ? actionMessage : ''" @submit="onCreate" />
    <PersonaSetRemoveDialog
      v-model="removeOpen"
      :name="removeTarget?.name ?? ''"
      :busy="busy"
      @confirm="onRemoveConfirm"
    />
  </div>
</template>

<style scoped>
.lps {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.lps__count {
  color: var(--fg2);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.lps__live {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}

.lps__live:empty {
  display: none;
}

.lps__text {
  margin: 0;
  color: var(--fg2);
  font-size: 13.5px;
}

.lps__text--fg {
  color: var(--fg);
}

.lps__err {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  max-width: 640px;
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--err-soft);
}

.lps__errtitle {
  margin: 0;
  color: var(--err);
  font-size: 15px;
  font-weight: 650;
}

.lps__empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  max-width: 560px;
  padding: 24px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
}

.lps__btn {
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

.lps__btn:hover {
  background: var(--s4);
}

.lps__btn--primary {
  background: var(--acc-text);
  color: var(--bg);
}

.lps__btn:focus-visible,
.lps__search:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.lps__search {
  max-width: 360px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
}

.lps__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
