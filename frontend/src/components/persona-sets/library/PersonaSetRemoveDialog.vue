<script setup lang="ts">
/**
 * Rückfrage vor dem Löschen eines Personasatzes (#1807, Etappe 7). Fokusfalle
 * und Fokus-Rückgabe liefert der gemeinsame `Dialog`; ESC bricht ab.
 */
import { useI18n } from 'vue-i18n'
import Dialog from '@/components/v4/data/Dialog.vue'
import { PersonaSetLibraryTestId as Id } from './libraryTestIds'

defineProps<{
  modelValue: boolean
  name: string
  busy: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

const { t } = useI18n()
</script>

<template>
  <Dialog
    :model-value="modelValue"
    :title="t('views.personaSets.library.remove.title')"
    size="sm"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p class="psr__body">{{ t('views.personaSets.library.remove.body', { name }) }}</p>
    <template #footer>
      <button type="button" class="psr__btn" :data-testid="Id.removeCancel" @click="emit('update:modelValue', false)">
        {{ t('views.personaSets.library.remove.cancel') }}
      </button>
      <button
        type="button"
        class="psr__btn psr__btn--danger"
        :disabled="busy"
        :data-testid="Id.removeConfirm"
        @click="emit('confirm')"
      >
        {{ t('views.personaSets.library.remove.confirm') }}
      </button>
    </template>
  </Dialog>
</template>

<style scoped>
.psr__body {
  margin: 0;
  overflow-wrap: anywhere;
}

.psr__btn {
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

.psr__btn--danger {
  background: var(--err);
  color: var(--bg);
}

.psr__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.psr__btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
