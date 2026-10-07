<script setup lang="ts">
/**
 * Abschnitt „Sprache und Ton“: Sprache der Persona. Ein eigenes Ton-/Stilfeld
 * gibt der Vertrag nicht her; der Hinweis sagt das offen.
 */
import { useI18n } from 'vue-i18n'
import EditorField from './EditorField.vue'
import { fieldDomId, type EditorDraft, type FieldMessages } from './editorModel'

defineProps<{ uid: string; errors: FieldMessages; readonly: boolean }>()
const draft = defineModel<EditorDraft>({ required: true })
const { t } = useI18n()
const p = 'views.personaSets.editor.fields'
</script>

<template>
  <div class="pe-grid">
    <p class="pe-note pe-grid__wide" data-testid="persona-editor-language-note">{{ t('views.personaSets.editor.sections.language.note') }}</p>
    <EditorField :id="fieldDomId(uid, 'language')" :label="t(`${p}.language.label`)" :hint="t(`${p}.language.hint`)" :error="errors.language" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.language" type="text" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
  </div>
</template>
