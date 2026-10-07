<script setup lang="ts">
/**
 * Abschnitt „Haltung und Ziele“: Persona-Beschreibung, Interessen, MBTI.
 * Der Vertrag kennt kein eigenes Haltungs- oder Zielfeld; der Hinweis sagt das offen.
 */
import { useI18n } from 'vue-i18n'
import EditorField from './EditorField.vue'
import { PROFILE_LIMITS, fieldDomId, type EditorDraft, type FieldMessages } from './editorModel'
import { PersonaMbtiSchema } from '@/contracts/personaSetContract'

defineProps<{ uid: string; errors: FieldMessages; readonly: boolean }>()
const draft = defineModel<EditorDraft>({ required: true })
const { t } = useI18n()
const p = 'views.personaSets.editor.fields'
</script>

<template>
  <div class="pe-grid">
    <p class="pe-note pe-grid__wide" data-testid="persona-editor-stance-note">{{ t('views.personaSets.editor.sections.stance.note') }}</p>
    <EditorField class="pe-grid__wide" :id="fieldDomId(uid, 'persona')" :label="t(`${p}.persona.label`)" :hint="t(`${p}.persona.hint`, { n: draft.persona.length, max: PROFILE_LIMITS.persona })" :error="errors.persona" v-slot="{ id, describedby, invalid }">
      <textarea :id="id" v-model="draft.persona" rows="10" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" />
    </EditorField>
    <EditorField class="pe-grid__wide" :id="fieldDomId(uid, 'interested_topics')" :label="t(`${p}.interested_topics.label`)" :hint="t(`${p}.interested_topics.hint`, { max: PROFILE_LIMITS.topics })" :error="errors.interested_topics" v-slot="{ id, describedby, invalid }">
      <textarea :id="id" v-model="draft.topics" rows="4" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'mbti')" :label="t(`${p}.mbti.label`)" :error="errors.mbti" v-slot="{ id, describedby, invalid }">
      <select :id="id" v-model="draft.mbti" class="pe-input" :disabled="readonly" :aria-invalid="invalid" :aria-describedby="describedby">
        <option value="">{{ t(`${p}.mbti.unset`) }}</option>
        <option v-for="m in PersonaMbtiSchema.options" :key="m" :value="m">{{ m }}</option>
      </select>
    </EditorField>
  </div>
</template>
