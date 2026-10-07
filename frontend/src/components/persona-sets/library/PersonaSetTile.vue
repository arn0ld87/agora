<script setup lang="ts">
/**
 * Kachel eines Personasatzes (#1807, Etappe 7): Name (Link auf den Satz),
 * Beschreibung, Anzahl Personas, Zustand, Verwendung, Änderungsdatum und die
 * Aktionen Duplizieren und Löschen. Ein gesperrter Satz lässt sich nicht
 * löschen: der Knopf ist deaktiviert und nennt den Grund.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PersonaSetSummary } from '@/contracts/personaSetContract'
import { IMPORTED_PERSONA_SET_ID, PersonaSetLibraryTestId as Id } from './libraryTestIds'

const props = defineProps<{
  set: PersonaSetSummary
  busy: boolean
}>()

defineEmits<{
  duplicate: [set: PersonaSetSummary]
  remove: [set: PersonaSetSummary]
}>()

const { t, locale } = useI18n()

const reasonId = computed(() => `persona-set-lock-reason-${props.set.id}`)
const isImported = computed(() => props.set.id === IMPORTED_PERSONA_SET_ID)

const personasText = computed(() =>
  props.set.entry_count === 1
    ? t('views.personaSets.library.personasOne')
    : t('views.personaSets.library.personas', { n: props.set.entry_count }),
)

const usageText = computed(() => {
  const n = props.set.usage_count
  if (n === 0) return t('views.personaSets.library.usageNone')
  return n === 1 ? t('views.personaSets.library.usageOne') : t('views.personaSets.library.usage', { n })
})

const dateText = computed(() => {
  const d = new Date(props.set.updated_at)
  const text = Number.isNaN(d.getTime())
    ? props.set.updated_at
    : d.toLocaleDateString(locale.value, { day: '2-digit', month: '2-digit', year: 'numeric' })
  return t('views.personaSets.library.updated', { date: text })
})
</script>

<template>
  <li class="pst" :data-testid="Id.tile" :data-set-id="set.id">
    <div class="pst__top">
      <span
        class="pst__chip"
        :class="{ 'pst__chip--locked': set.locked }"
        :data-testid="set.locked ? Id.tileLocked : undefined"
      >
        {{ set.locked ? t('views.personaSets.library.stateLocked') : t('views.personaSets.library.stateEditable') }}
      </span>
      <span class="pst__date">{{ dateText }}</span>
    </div>

    <h3 class="pst__name">
      <RouterLink class="pst__link" :to="{ name: 'PersonaSet', params: { setId: set.id } }" :data-testid="Id.tileOpen">
        {{ set.name }}
      </RouterLink>
    </h3>

    <p v-if="set.description" class="pst__desc">{{ set.description }}</p>
    <p v-if="isImported" class="pst__note" :data-testid="Id.importedNote">
      {{ t('views.personaSets.library.importedNote') }}
    </p>

    <p class="pst__meta">
      <span>{{ personasText }}</span>
      <span>{{ usageText }}</span>
    </p>

    <div class="pst__actions" role="group" :aria-label="t('views.personaSets.library.tileActions', { name: set.name })">
      <button type="button" class="pst__btn" :data-testid="Id.tileDuplicate" :disabled="busy" @click="$emit('duplicate', set)">
        {{ t('views.personaSets.library.duplicate') }}
      </button>
      <button
        type="button"
        class="pst__btn pst__btn--danger"
        :data-testid="Id.tileDelete"
        :disabled="busy || set.locked"
        :aria-describedby="set.locked ? reasonId : undefined"
        @click="$emit('remove', set)"
      >
        {{ t('views.personaSets.library.delete') }}
      </button>
    </div>
    <p v-if="set.locked" :id="reasonId" class="pst__reason">
      {{ t('views.personaSets.library.deleteLockedReason') }}
    </p>
  </li>
</template>

<style scoped>
.pst {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 16px 18px;
  border-radius: var(--ag-r-12);
  background: var(--s2);
  color: var(--fg);
}

.pst:hover,
.pst:focus-within {
  background: var(--s3);
}

.pst__top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pst__chip {
  padding: 2px 10px;
  border-radius: var(--ag-r-pill);
  background: var(--s3);
  color: var(--fg2);
  font-size: 12px;
  font-weight: 600;
}

.pst__chip--locked {
  background: var(--warn-soft);
  color: var(--warn);
}

.pst__date {
  margin-left: auto;
  color: var(--fg3);
  font-size: 12.5px;
}

.pst__name {
  margin: 0;
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.pst__link {
  color: inherit;
  text-decoration: none;
}

.pst__link:hover {
  text-decoration: underline;
}

.pst__link:focus-visible,
.pst__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.pst__desc,
.pst__note,
.pst__reason {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.pst__note {
  padding: 8px 10px;
  border-radius: var(--ag-r-8);
  background: var(--s3);
}

.pst__reason {
  color: var(--fg3);
  font-size: 12.5px;
}

.pst__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}

.pst__actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}

.pst__btn {
  height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.pst__btn:hover:not(:disabled) {
  background: var(--s4);
}

.pst__btn--danger {
  color: var(--err);
}

.pst__btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
