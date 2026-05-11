<script setup lang="ts">
/**
 * AddPersonaModal — manuelles Persona-Anlegen, extrahiert aus Step2EnvSetup.vue.
 *
 * Sub-Slice 41 (Refs #203): Isoliert den Add-Persona-Modal-Block aus
 * Step2EnvSetup.vue.
 *
 * Strings via vue-i18n. Pure UI-Komponente, keine API-Aufrufe.
 */
import { useI18n } from 'vue-i18n'
import Btn from '../ui/Btn.vue'

export interface NewPersonaForm {
  username: string
  name: string
  bio: string
  persona: string
  profession: string
  country: string
  age: number | null
  gender: 'other' | 'female' | 'male'
  mbti: string
  interested_topics: string // CSV-String, wird im Composable in Array konvertiert
}

interface Props {
  open: boolean
  persona: NewPersonaForm
  saving: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  'update:persona': [value: NewPersonaForm]
  submit: []
}>()

const { t } = useI18n()

function close() {
  emit('update:open', false)
}

function updateField<K extends keyof NewPersonaForm>(key: K, value: NewPersonaForm[K]) {
  emit('update:persona', { ...props.persona, [key]: value })
}

function inputValue(event: Event): string {
  return (event.target as HTMLInputElement).value
}

function textareaValue(event: Event): string {
  return (event.target as HTMLTextAreaElement).value
}

function updateAge(event: Event) {
  const value = inputValue(event)
  updateField('age', value === '' ? null : Number(value))
}

function updateGender(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (value === 'other' || value === 'female' || value === 'male') {
    updateField('gender', value)
  }
}
</script>

<template>
  <div v-if="open" class="modal" @click.self="close">
    <div class="modal-card">
      <header class="modal-head">
        <div>
          <div class="kicker-mono">{{ t('step2.addPersona.kicker') }}</div>
          <h3>{{ t('step2.addPersona.title') }}</h3>
        </div>
        <button class="x" @click="close" :aria-label="t('common.close')">×</button>
      </header>

      <div class="form-grid">
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.username') }} *</span>
          <input
            :value="persona.username"
            @input="updateField('username', inputValue($event))"
            type="text"
            :placeholder="t('step2.addPersona.placeholders.username')"
          />
        </label>
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.name') }}</span>
          <input
            :value="persona.name"
            @input="updateField('name', inputValue($event))"
            type="text"
            :placeholder="t('step2.addPersona.placeholders.name')"
          />
        </label>
        <label class="form-row form-row--wide">
          <span>{{ t('step2.addPersona.fields.bio') }}</span>
          <input
            :value="persona.bio"
            @input="updateField('bio', inputValue($event))"
            type="text"
            maxlength="150"
            :placeholder="t('step2.addPersona.placeholders.bio')"
          />
        </label>
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.profession') }}</span>
          <input
            :value="persona.profession"
            @input="updateField('profession', inputValue($event))"
            type="text"
            :placeholder="t('step2.addPersona.placeholders.profession')"
          />
        </label>
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.country') }}</span>
          <input
            :value="persona.country"
            @input="updateField('country', inputValue($event))"
            type="text"
            maxlength="4"
            :placeholder="t('step2.addPersona.placeholders.country')"
          />
        </label>
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.age') }}</span>
          <input
            :value="persona.age ?? ''"
            @input="updateAge"
            type="number"
            min="15"
            max="99"
          />
        </label>
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.gender') }}</span>
          <select
            :value="persona.gender"
            @change="updateGender"
          >
            <option value="other">other</option>
            <option value="female">female</option>
            <option value="male">male</option>
          </select>
        </label>
        <label class="form-row">
          <span>{{ t('step2.addPersona.fields.mbti') }}</span>
          <input
            :value="persona.mbti"
            @input="updateField('mbti', inputValue($event))"
            type="text"
            maxlength="4"
            placeholder="INTJ"
          />
        </label>
        <label class="form-row form-row--wide">
          <span>{{ t('step2.addPersona.fields.topics') }}</span>
          <input
            :value="persona.interested_topics"
            @input="updateField('interested_topics', inputValue($event))"
            type="text"
            :placeholder="t('step2.addPersona.placeholders.topics')"
          />
        </label>
        <label class="form-row form-row--wide">
          <span>{{ t('step2.addPersona.fields.persona') }}</span>
          <textarea
            :value="persona.persona"
            @input="updateField('persona', textareaValue($event))"
            rows="6"
            :placeholder="t('step2.addPersona.placeholders.persona')"
          />
        </label>
      </div>

      <div class="actions">
        <Btn variant="ghost" @click="close">{{ t('common.cancel') }}</Btn>
        <Btn
          variant="primary"
          :loading="saving"
          :disabled="!persona.username.trim() || saving"
          @click="emit('submit')"
        >{{ t('step2.addPersona.submit') }}</Btn>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Modal-Layout-Styles — Option 1: kopiert aus Step2EnvSetup.vue (scoped-CSS-Boundary).
   Step2EnvSetup.vue behält diese Klassen für den Detail-Modal. */

.modal {
  position: fixed; inset: 0;
  background: color-mix(in srgb, var(--bg) 60%, transparent);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  padding: var(--s-5);
}
.modal-card {
  background: var(--bg);
  border: 1px solid var(--rule-strong);
  padding: var(--s-7);
  max-width: 880px;
  max-height: 85vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  border-radius: var(--r-1);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.kicker-mono {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: var(--s-2);
}
.modal-head h3 {
  font-family: var(--ff-sans);
  font-weight: 650;
  font-size: clamp(2rem, 4vw, 3rem);
  line-height: 1.1;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--fg);
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.form-row--wide { grid-column: 1 / -1; }
.form-row input,
.form-row select,
.form-row textarea {
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  color: var(--fg);
  font-family: var(--ff-sans);
  font-size: var(--fs-14);
  padding: 8px 10px;
  text-transform: none;
  letter-spacing: normal;
  outline: none;
}
.form-row textarea { resize: vertical; font-family: var(--ff-sans); line-height: 1.4; }
.form-row input:focus,
.form-row select:focus,
.form-row textarea:focus { border-color: var(--accent); }
@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
}
.actions {
  display: flex;
  gap: var(--s-3);
  justify-content: flex-end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-4);
}
.x {
  background: transparent;
  border: 0;
  font-size: 24px;
  cursor: pointer;
  color: var(--fg-muted);
}
.x:hover { color: var(--accent); }

/* Design v3 form polish. */
.form-row {
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
  color: var(--text-secondary, var(--fg-muted));
  font-weight: 590;
}
.form-row input,
.form-row select,
.form-row textarea {
  background: var(--surface-elevated, var(--bg-elevated));
  border-color: var(--hairline, var(--rule));
  border-radius: var(--r-5, var(--r-1));
  color: var(--text-primary, var(--fg));
  font-family: var(--font-sans, var(--ff-sans));
}
.form-row textarea {
  font-family: var(--font-sans, var(--ff-sans));
}
.form-row input:focus,
.form-row select:focus,
.form-row textarea:focus {
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}
</style>
