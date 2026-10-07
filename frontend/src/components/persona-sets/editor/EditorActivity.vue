<script setup lang="ts">
/** Abschnitt „Aktivität“: Aktivitätsniveau (0 bis 1) und Zeitzone. */
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
    <EditorField :id="fieldDomId(uid, 'activity_level')" :label="t(`${p}.activity_level.label`)" :hint="t(`${p}.activity_level.hint`)" :error="errors.activity_level" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.activity_level" type="text" inputmode="decimal" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'time_zone')" :label="t(`${p}.time_zone.label`)" :hint="t(`${p}.time_zone.hint`)" :error="errors.time_zone" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.time_zone" type="text" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
  </div>
</template>
