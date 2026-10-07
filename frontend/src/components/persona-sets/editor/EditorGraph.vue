<script setup lang="ts">
/**
 * Abschnitt „Bezug zum Graphen“: Herkunft und Quell-Entität-UUID sind lesend
 * (die Eingabeform des Vertrags enthält sie nicht, der Aufrufer setzt sie),
 * der Quell-Entitätstyp ist editierbar.
 */
import { useI18n } from 'vue-i18n'
import type { PersonaOrigin } from '@/contracts/personaSetContract'
import EditorField from './EditorField.vue'
import { fieldDomId, type EditorDraft, type FieldMessages } from './editorModel'

defineProps<{
  uid: string
  errors: FieldMessages
  readonly: boolean
  origin: PersonaOrigin
  sourceEntityUuid: string | null
}>()
const draft = defineModel<EditorDraft>({ required: true })
const { t } = useI18n()
const p = 'views.personaSets.editor.fields'
</script>

<template>
  <div class="pe-grid">
    <p class="pe-note pe-grid__wide">{{ t('views.personaSets.editor.sections.graph.note') }}</p>
    <dl class="pe-dl pe-grid__wide">
      <dt>{{ t(`${p}.origin.label`) }}</dt>
      <dd data-testid="persona-editor-graph-origin">{{ t(`views.personaSets.detail.origin.${origin}`) }}</dd>
      <dt>{{ t(`${p}.source_entity_uuid.label`) }}</dt>
      <dd data-testid="persona-editor-graph-uuid">
        <code v-if="sourceEntityUuid">{{ sourceEntityUuid }}</code>
        <template v-else>{{ t(`${p}.source_entity_uuid.none`) }}</template>
      </dd>
    </dl>
    <EditorField :id="fieldDomId(uid, 'source_entity_type')" :label="t(`${p}.source_entity_type.label`)" :hint="t(`${p}.source_entity_type.hint`)" :error="errors.source_entity_type" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.source_entity_type" type="text" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
  </div>
</template>
