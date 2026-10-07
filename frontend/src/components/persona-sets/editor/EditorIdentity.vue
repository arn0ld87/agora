<script setup lang="ts">
/** Abschnitt „Identität“: Name, Benutzername, Art, Rolle, Alter, Geschlecht, Land, Ort, Kurzprofil, Verifiziert. */
import { useI18n } from 'vue-i18n'
import EditorField from './EditorField.vue'
import { PROFILE_LIMITS, fieldDomId, type EditorDraft, type FieldMessages } from './editorModel'

defineProps<{ uid: string; errors: FieldMessages; readonly: boolean }>()
const draft = defineModel<EditorDraft>({ required: true })
const { t } = useI18n()
const p = 'views.personaSets.editor.fields'
</script>

<template>
  <div class="pe-grid">
    <EditorField :id="fieldDomId(uid, 'name')" :label="t(`${p}.name.label`)" required :error="errors.name" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.name" type="text" class="pe-input" :readonly="readonly" aria-required="true" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" data-testid="persona-editor-name" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'username')" :label="t(`${p}.username.label`)" required :hint="t(`${p}.username.hint`)" :error="errors.username" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.username" type="text" class="pe-input" :readonly="readonly" aria-required="true" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" data-testid="persona-editor-username" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'persona_kind')" :label="t(`${p}.persona_kind.label`)" :error="errors.persona_kind" v-slot="{ id, describedby, invalid }">
      <select :id="id" v-model="draft.persona_kind" class="pe-input" :disabled="readonly" :aria-invalid="invalid" :aria-describedby="describedby">
        <option value="individual">{{ t('views.personaSets.detail.kind.individual') }}</option>
        <option value="collective">{{ t('views.personaSets.detail.kind.collective') }}</option>
      </select>
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'profession')" :label="t(`${p}.profession.label`)" :error="errors.profession" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.profession" type="text" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'age')" :label="t(`${p}.age.label`)" :hint="t(`${p}.age.hint`, { max: PROFILE_LIMITS.ageMax })" :error="errors.age" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.age" type="text" inputmode="numeric" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'gender')" :label="t(`${p}.gender.label`)" :error="errors.gender" v-slot="{ id, describedby, invalid }">
      <select :id="id" v-model="draft.gender" class="pe-input" :disabled="readonly" :aria-invalid="invalid" :aria-describedby="describedby">
        <option value="">{{ t(`${p}.gender.unset`) }}</option>
        <option v-for="g in ['male', 'female', 'nonbinary', 'other']" :key="g" :value="g">{{ t(`${p}.gender.options.${g}`) }}</option>
      </select>
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'country')" :label="t(`${p}.country.label`)" :hint="t(`${p}.country.hint`)" :error="errors.country" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.country" type="text" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
    <EditorField :id="fieldDomId(uid, 'location')" :label="t(`${p}.location.label`)" :error="errors.location" v-slot="{ id, describedby, invalid }">
      <input :id="id" v-model="draft.location" type="text" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" autocomplete="off" />
    </EditorField>
    <EditorField class="pe-grid__wide" :id="fieldDomId(uid, 'bio')" :label="t(`${p}.bio.label`)" :hint="t(`${p}.bio.hint`, { n: draft.bio.length, max: PROFILE_LIMITS.bio })" :error="errors.bio" v-slot="{ id, describedby, invalid }">
      <textarea :id="id" v-model="draft.bio" rows="3" class="pe-input" :readonly="readonly" :aria-invalid="invalid" :aria-describedby="describedby" />
    </EditorField>
    <div class="pe-grid__wide pe-check">
      <input :id="fieldDomId(uid, 'verified')" v-model="draft.verified" type="checkbox" :disabled="readonly" :aria-describedby="`${fieldDomId(uid, 'verified')}-hint`" />
      <label :for="fieldDomId(uid, 'verified')">{{ t(`${p}.verified.label`) }}</label>
      <p :id="`${fieldDomId(uid, 'verified')}-hint`" class="pe-field__hint">{{ t(`${p}.verified.hint`) }}</p>
    </div>
  </div>
</template>
