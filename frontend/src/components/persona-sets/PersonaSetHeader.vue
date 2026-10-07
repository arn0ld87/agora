<script setup lang="ts">
/**
 * Kopf der Satz-Ansicht (#1807, E7-F2): Name und Beschreibung (auch bei
 * gesperrtem Satz umbenennbar, das Backend sperrt nur Personas), Anzahl,
 * Zustand, nutzende Läufe, Duplizieren und der Sperrhinweis mit Ausweg.
 */
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Badge from '@/components/ui/Badge.vue'
import type { PersonaSetRecord } from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from './detailTestIds'
import { PersonaSetTestId } from '@/contracts/testIds'

const props = defineProps<{ record: PersonaSetRecord; locked: boolean; busy: boolean; duplicateError: string | null }>()
const emit = defineEmits<{
  (e: 'rename', payload: { name: string; description: string }): void
  (e: 'duplicate'): void
}>()
const { t } = useI18n()

const editing = ref(false)
const name = ref('')
const description = ref('')
const nameField = ref<HTMLInputElement | null>(null)
const renameButton = ref<HTMLButtonElement | null>(null)

async function startEdit(): Promise<void> {
  name.value = props.record.name
  description.value = props.record.description
  editing.value = true
  await nextTick()
  nameField.value?.focus()
}

async function stopEdit(): Promise<void> {
  editing.value = false
  await nextTick()
  renameButton.value?.focus()
}

async function saveEdit(): Promise<void> {
  if (name.value.trim() === '') return
  emit('rename', { name: name.value.trim(), description: description.value })
  await stopEdit()
}
</script>

<template>
  <section class="phead" :data-testid="Id.header" :aria-label="t('views.personaSets.detail.header.label')">
    <div v-if="!editing" class="phead__main">
      <h2 class="phead__name">{{ record.name }}</h2>
      <p v-if="record.description" class="phead__desc">{{ record.description }}</p>
      <button ref="renameButton" type="button" :disabled="busy" :data-testid="Id.rename" @click="startEdit">
        {{ t('views.personaSets.detail.header.rename') }}
      </button>
    </div>
    <form v-else class="phead__edit" @submit.prevent="saveEdit" @keydown.esc="stopEdit">
      <label>
        {{ t('views.personaSets.detail.header.name') }}
        <input ref="nameField" v-model="name" type="text" maxlength="120" required :data-testid="Id.nameInput" />
      </label>
      <label>
        {{ t('views.personaSets.detail.header.description') }}
        <textarea v-model="description" maxlength="2000" rows="2" />
      </label>
      <button type="submit" :disabled="busy" :data-testid="Id.nameSave">{{ t('views.personaSets.detail.header.save') }}</button>
      <button type="button" @click="stopEdit">{{ t('views.personaSets.detail.header.cancel') }}</button>
    </form>

    <p class="phead__facts">
      <span :data-testid="Id.count">{{ t('views.personaSets.detail.header.count', { n: record.entries.length }) }}</span>
      <Badge :variant="locked ? 'warn' : 'success'" :data-testid="Id.state">
        <span aria-hidden="true">{{ locked ? '⊘' : '✎' }}</span>
        {{ locked ? t('views.personaSets.detail.header.stateLocked') : t('views.personaSets.detail.header.stateEditable') }}
      </Badge>
      <button type="button" :disabled="busy" :data-testid="Id.duplicate" @click="emit('duplicate')">
        {{ t('views.personaSets.detail.header.duplicate') }}
      </button>
    </p>
    <p v-if="duplicateError" role="alert" :data-testid="Id.duplicateError">{{ duplicateError }}</p>

    <div v-if="record.used_by_simulation_ids.length > 0" :data-testid="Id.usedBy">
      <p class="phead__used">{{ t('views.personaSets.detail.header.usedBy') }}</p>
      <ul>
        <li v-for="id in record.used_by_simulation_ids" :key="id">
          <RouterLink :to="{ name: 'Simulation', params: { simulationId: id } }">{{ id }}</RouterLink>
        </li>
      </ul>
    </div>

    <div v-if="locked" class="phead__lock" role="status" :data-testid="Id.lockNotice">
      <p :data-testid="PersonaSetTestId.locked">{{ t('views.personaSets.detail.locked') }}</p>
      <button type="button" :disabled="busy" :data-testid="Id.lockDuplicate" @click="emit('duplicate')">
        {{ t('views.personaSets.detail.header.duplicateAndEdit') }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.phead { display: flex; flex-direction: column; gap: var(--sp-3, 12px); margin-bottom: var(--sp-6, 24px); }
.phead__name { margin: 0; }
.phead__desc { color: var(--text-secondary, var(--fg-muted)); margin: 0; }
.phead__edit { display: flex; flex-direction: column; gap: var(--sp-2, 8px); max-width: 480px; }
.phead__facts { display: flex; align-items: center; gap: var(--sp-3, 12px); margin: 0; }
.phead__lock {
  padding: var(--sp-4, 16px);
  border: 2px solid var(--hairline-strong, var(--hairline));
  border-radius: var(--r-7, var(--r-3));
  background: var(--surface-elevated, var(--bg-elevated));
}
</style>
