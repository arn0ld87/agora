<script setup lang="ts">
/**
 * Dialog „Neuer Personasatz“ (#1807, Etappe 7): Name (Pflicht) und Beschreibung
 * (optional) mit den Längen des Vertrags. Fokusfalle und Fokus-Rückgabe liefert
 * der gemeinsame `Dialog`. Das Anlegen selbst übernimmt der Aufrufer.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Dialog from '@/components/v4/data/Dialog.vue'
import {
  PERSONA_SET_DESCRIPTION_MAX_LENGTH,
  PERSONA_SET_NAME_MAX_LENGTH,
} from '@/contracts/personaSetContract'
import { PersonaSetLibraryTestId as Id } from './libraryTestIds'

const props = defineProps<{
  modelValue: boolean
  busy: boolean
  /** Fehler der letzten Aktion (leer = keiner); bleibt im Dialog sichtbar. */
  error?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [value: { name: string; description: string }]
}>()

const { t } = useI18n()

const name = ref('')
const description = ref('')
const submitted = ref(false)

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      name.value = ''
      description.value = ''
      submitted.value = false
    }
  },
)

const nameError = computed<string | null>(() => {
  const trimmed = name.value.trim()
  if (trimmed.length === 0) return t('views.personaSets.library.create.nameRequired')
  if (trimmed.length > PERSONA_SET_NAME_MAX_LENGTH) {
    return t('views.personaSets.library.create.nameTooLong', { max: PERSONA_SET_NAME_MAX_LENGTH })
  }
  return null
})

const descriptionError = computed<string | null>(() =>
  description.value.length > PERSONA_SET_DESCRIPTION_MAX_LENGTH
    ? t('views.personaSets.library.create.descriptionTooLong', { max: PERSONA_SET_DESCRIPTION_MAX_LENGTH })
    : null,
)

function submit(): void {
  submitted.value = true
  if (props.busy || nameError.value || descriptionError.value) return
  emit('submit', { name: name.value.trim(), description: description.value })
}
</script>

<template>
  <Dialog
    :model-value="modelValue"
    :title="t('views.personaSets.library.create.title')"
    :description="t('views.personaSets.library.create.description')"
    size="md"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <form class="psd" novalidate @submit.prevent="submit">
      <label class="psd__field">
        <span class="psd__label">{{ t('views.personaSets.library.create.nameLabel') }}</span>
        <input
          v-model="name"
          class="psd__input"
          type="text"
          required
          :maxlength="PERSONA_SET_NAME_MAX_LENGTH * 2"
          :aria-invalid="submitted && nameError ? 'true' : undefined"
          :aria-describedby="submitted && nameError ? 'psd-name-error' : undefined"
          :data-testid="Id.createName"
        />
      </label>
      <p v-if="submitted && nameError" id="psd-name-error" class="psd__error" role="alert" :data-testid="Id.createNameError">
        {{ nameError }}
      </p>

      <label class="psd__field">
        <span class="psd__label">{{ t('views.personaSets.library.create.descriptionLabel') }}</span>
        <textarea
          v-model="description"
          class="psd__input psd__input--area"
          rows="3"
          :aria-invalid="descriptionError ? 'true' : undefined"
          :aria-describedby="descriptionError ? 'psd-desc-error' : undefined"
          :data-testid="Id.createDescription"
        />
      </label>
      <p v-if="descriptionError" id="psd-desc-error" class="psd__error" role="alert">{{ descriptionError }}</p>
      <p v-if="error" class="psd__error" role="alert" data-testid="persona-set-create-error">{{ error }}</p>
    </form>

    <template #footer>
      <button type="button" class="psd__btn" :data-testid="Id.createCancel" @click="emit('update:modelValue', false)">
        {{ t('views.personaSets.library.create.cancel') }}
      </button>
      <button
        type="button"
        class="psd__btn psd__btn--primary"
        :disabled="busy"
        :aria-busy="busy ? 'true' : undefined"
        :data-testid="Id.createSubmit"
        @click="submit"
      >
        {{ busy ? t('views.personaSets.library.create.submitting') : t('views.personaSets.library.create.submit') }}
      </button>
    </template>
  </Dialog>
</template>

<style scoped>
.psd {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.psd__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.psd__label {
  color: var(--text-secondary);
  font-size: 12.5px;
  font-weight: 500;
}

.psd__input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated);
  color: var(--text-primary);
  font: inherit;
  font-size: 14px;
}

.psd__input--area {
  resize: vertical;
}

.psd__input:focus-visible,
.psd__btn:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.psd__input[aria-invalid='true'] {
  border-color: var(--err);
}

.psd__error {
  margin: -6px 0 0;
  color: var(--err);
  font-size: 12.5px;
}

.psd__btn {
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

.psd__btn--primary {
  background: var(--acc-text);
  color: var(--bg);
}

.psd__btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
