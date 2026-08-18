<script setup lang="ts">
/**
 * PersonaDetailModal — Persona-Review-Drawer mit Approve/Reject/Regenerate/Edit.
 *
 * Sub-Slice 42 (Refs #203): Isoliert den Detail-Modal-Block aus Step2EnvSetup.vue.
 *
 * Pure UI-Komponente — keine eigene Composable-Instanziierung. Eltern reicht
 * State und Helper aus `usePersonaActions(...)` durch (Single-Source-of-Truth).
 */
import { useI18n } from 'vue-i18n'
import Button from '@/components/v4/forms/Button.vue'
import Badge from '../ui/Badge.vue'

interface ReviewIssue {
  code: string
  severity: string
  detail?: { missing?: string[] }
}

interface EditableProfile {
  name?: string
  profession?: string
  bio?: string
  country?: string
  age?: number | null
  gender?: string
  mbti?: string
  interested_topics?: string | string[]
  persona?: string
}

interface Props {
  selectedProfile: any | null
  editingProfile: EditableProfile | null
  reviewActionPending: boolean
  reviewActionError: string
  regenerateHint: string
  reviewEnabled: boolean
  // helper functions injected — kommen aus usePersonaActions/usePersonaReview
  statusVariant: (status: string) => string
  statusLabel: (status: string) => string
  issueBadgeVariant: (severity: string) => string
  getIssuesFor: (username: string) => ReviewIssue[]
  highestSeverityFor: (username: string) => string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:selectedProfile': [value: any | null]
  'update:editingProfile': [value: EditableProfile | null]
  'update:regenerateHint': [value: string]
  'start-editing': []
  'cancel-editing': []
  approve: []
  reject: []
  regenerate: []
  save: []
}>()

const { t } = useI18n()

function close() {
  emit('update:selectedProfile', null)
  emit('cancel-editing')
}

function updateEditField<K extends keyof EditableProfile>(key: K, value: EditableProfile[K]) {
  if (!props.editingProfile) return
  emit('update:editingProfile', { ...props.editingProfile, [key]: value })
}

function inputValue(event: Event): string {
  return (event.target as HTMLInputElement).value
}

function textareaValue(event: Event): string {
  return (event.target as HTMLTextAreaElement).value
}

function updateRegenerateHint(event: Event) {
  emit('update:regenerateHint', inputValue(event))
}

function updateEditAge(event: Event) {
  const value = inputValue(event)
  updateEditField('age', value === '' ? null : Number(value))
}

function updateEditGender(event: Event) {
  updateEditField('gender', (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <div v-if="selectedProfile" class="modal" @click.self="close">
    <div class="modal-card">
      <header class="modal-head">
        <div>
          <div class="kicker-mono">{{ t('step2.detailModal.kicker') }}</div>
          <h3>{{ selectedProfile.name || selectedProfile.username }}</h3>
          <div
            v-if="selectedProfile.username && selectedProfile.name && selectedProfile.username !== selectedProfile.name"
            class="modal-handle"
          >@{{ selectedProfile.username }}</div>
        </div>
        <button class="x" @click="close" :aria-label="t('common.close')">×</button>
      </header>

      <!-- Review-Bar mit Action-Buttons -->
      <div class="review-bar">
        <Badge
          v-if="selectedProfile.review_status"
          :variant="statusVariant(selectedProfile.review_status)"
          dot
        >{{ statusLabel(selectedProfile.review_status) }}</Badge>
        <span v-if="reviewEnabled" class="meta">{{ t('step2.detailModal.reviewActive') }}</span>
        <span class="review-bar-spacer" />
        <template v-if="!editingProfile">
          <Button variant="ghost" :disabled="reviewActionPending" @click="emit('start-editing')">{{ t('step2.detailModal.actions.edit') }}</Button>
          <Button variant="ghost" :disabled="reviewActionPending" @click="emit('reject')">{{ t('step2.detailModal.actions.reject') }}</Button>
          <Button
            variant="ghost"
            :disabled="reviewActionPending"
            :loading="reviewActionPending && selectedProfile?.review_status === 'regenerating'"
            @click="emit('regenerate')"
          >{{ t('step2.persona.regenerate') }}</Button>
          <Button variant="primary" :disabled="reviewActionPending" @click="emit('approve')">{{ t('step2.detailModal.actions.approve') }}</Button>
        </template>
        <template v-else>
          <Button variant="ghost" :disabled="reviewActionPending" @click="emit('cancel-editing')">{{ t('common.cancel') }}</Button>
          <Button
            variant="primary"
            :loading="reviewActionPending"
            :disabled="reviewActionPending"
            @click="emit('save')"
          >{{ t('step2.detailModal.actions.save') }}</Button>
        </template>
      </div>

      <!-- Issue-Liste -->
      <ul v-if="getIssuesFor(selectedProfile.username).length" class="review-issues">
        <li
          v-for="issue in getIssuesFor(selectedProfile.username)"
          :key="issue.code"
        >
          <Badge :variant="issueBadgeVariant(issue.severity)">{{ issue.severity }}</Badge>
          <span>{{ issue.code }}</span>
          <span v-if="issue.detail?.missing" class="meta">→ {{ issue.detail.missing.join(', ') }}</span>
        </li>
      </ul>

      <!-- Regenerate-Hint-Input -->
      <div v-if="!editingProfile" class="regenerate-hint-row">
        <input
          :value="regenerateHint"
          @input="updateRegenerateHint"
          type="text"
          class="regenerate-hint-input"
          :placeholder="t('step2.persona.regenerateHint')"
          :disabled="reviewActionPending"
        />
      </div>
      <p v-if="reviewActionError" class="meta review-error">{{ reviewActionError }}</p>

      <!-- Read-only View -->
      <template v-if="!editingProfile">
        <p class="modal-bio">{{ selectedProfile.bio }}</p>
        <div class="modal-marginalia">
          <dl>
            <div v-if="selectedProfile.age">
              <dt>{{ t('step2.detailModal.fields.age') }}</dt>
              <dd>{{ selectedProfile.age }}</dd>
            </div>
            <div v-if="selectedProfile.gender">
              <dt>{{ t('step2.detailModal.fields.gender') }}</dt>
              <dd>{{ selectedProfile.gender }}</dd>
            </div>
            <div v-if="selectedProfile.mbti">
              <dt>{{ t('step2.detailModal.fields.mbti') }}</dt>
              <dd class="mono-big">{{ selectedProfile.mbti }}</dd>
            </div>
            <div v-if="selectedProfile.country">
              <dt>{{ t('step2.detailModal.fields.country') }}</dt>
              <dd>{{ selectedProfile.country }}</dd>
            </div>
            <div v-if="selectedProfile.profession">
              <dt>{{ t('step2.detailModal.fields.profession') }}</dt>
              <dd>{{ selectedProfile.profession }}</dd>
            </div>
          </dl>
          <div class="modal-content">
            <div v-if="selectedProfile.interested_topics?.length" class="topic-chips">
              <span class="kicker-mono">{{ t('step5.agent.interests') }}</span>
              <div class="chips">
                <span v-for="topic in selectedProfile.interested_topics" :key="topic" class="chip">
                  {{ topic }}
                </span>
              </div>
            </div>
            <p class="modal-persona" v-if="selectedProfile.persona">{{ selectedProfile.persona }}</p>
          </div>
        </div>
      </template>

      <!-- Edit-Form -->
      <div v-else class="form-grid">
        <label class="form-row">
          <span>{{ t('step2.detailModal.fields.displayName') }}</span>
          <input :value="editingProfile.name" @input="updateEditField('name', inputValue($event))" type="text" />
        </label>
        <label class="form-row">
          <span>{{ t('step2.detailModal.fields.profession') }}</span>
          <input :value="editingProfile.profession" @input="updateEditField('profession', inputValue($event))" type="text" />
        </label>
        <label class="form-row form-row--wide">
          <span>{{ t('step2.detailModal.fields.bioShort') }}</span>
          <input :value="editingProfile.bio" @input="updateEditField('bio', inputValue($event))" type="text" maxlength="200" />
        </label>
        <label class="form-row">
          <span>{{ t('step2.detailModal.fields.country') }}</span>
          <input :value="editingProfile.country" @input="updateEditField('country', inputValue($event))" type="text" maxlength="4" />
        </label>
        <label class="form-row">
          <span>{{ t('step2.detailModal.fields.age') }}</span>
          <input :value="editingProfile.age ?? ''" @input="updateEditAge" type="number" min="15" max="99" />
        </label>
        <label class="form-row">
          <span>{{ t('step2.detailModal.fields.gender') }}</span>
          <select :value="editingProfile.gender" @change="updateEditGender">
            <option value="other">other</option>
            <option value="female">female</option>
            <option value="male">male</option>
          </select>
        </label>
        <label class="form-row">
          <span>{{ t('step2.detailModal.fields.mbti') }}</span>
          <input :value="editingProfile.mbti" @input="updateEditField('mbti', inputValue($event))" type="text" maxlength="4" />
        </label>
        <label class="form-row form-row--wide">
          <span>{{ t('step2.detailModal.fields.topicsCsv') }}</span>
          <input :value="editingProfile.interested_topics" @input="updateEditField('interested_topics', inputValue($event))" type="text" />
        </label>
        <label class="form-row form-row--wide">
          <span>{{ t('step2.detailModal.fields.personaLong') }}</span>
          <textarea :value="editingProfile.persona" @input="updateEditField('persona', textareaValue($event))" rows="6"></textarea>
        </label>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Modal-bezogene Klassen, gespiegelt aus Step2EnvSetup.vue (scoped-CSS-Boundary).
   Step2EnvSetup.vue behält diese Klassen für etwaige andere Modal-Verwendung. */

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
.modal-handle {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  color: var(--fg-muted);
  letter-spacing: var(--ls-mono);
  margin-top: var(--s-1);
}
.x {
  background: transparent;
  border: 0;
  font-size: 24px;
  cursor: pointer;
  color: var(--fg-muted);
}
.x:hover { color: var(--accent); }
.review-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--rule);
}
.review-bar-spacer { flex: 1; }
.review-issues {
  list-style: none;
  margin: var(--s-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.review-issues li {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--font-mono-sm);
  color: var(--fg-body);
}
.review-error {
  color: var(--status-error);
  margin-top: var(--s-2);
}
.regenerate-hint-row {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.regenerate-hint-input {
  flex: 1;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  padding: 4px 0;
  color: var(--fg);
  outline: none;
}
.regenerate-hint-input:focus { border-bottom-color: var(--accent); }
.regenerate-hint-input::placeholder { color: var(--fg-muted); }
.regenerate-hint-input:disabled { opacity: 0.5; cursor: not-allowed; }
.modal-bio {
  font-family: var(--ff-sans);
  font-weight: 400;
  font-size: var(--fs-18);
  line-height: 1.5;
  color: var(--fg-body);
  margin: 0;
  border-left: 2px solid var(--accent);
  padding-left: var(--s-4);
}
.modal-marginalia {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: var(--s-7);
  border-top: 1px solid var(--rule);
  padding-top: var(--s-5);
}
.modal-marginalia dl {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin: 0;
}
.modal-marginalia dt {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: 2px;
}
.modal-marginalia dd {
  margin: 0;
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  color: var(--fg);
}
.modal-marginalia dd.mono-big {
  font-family: var(--ff-mono);
  font-size: var(--fs-20);
  font-weight: 500;
  color: var(--accent);
}
.modal-content {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}
.topic-chips { display: flex; flex-direction: column; gap: var(--s-2); }
.topic-chips .chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.topic-chips .chip {
  display: inline-block;
  padding: 4px 10px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  border: 1px solid var(--rule-strong);
  background: transparent;
  color: var(--fg);
  border-radius: var(--r-pill);
}
.modal-persona {
  white-space: pre-wrap;
  color: var(--fg-body);
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  line-height: 1.65;
  margin: 0;
}
@media (max-width: 720px) {
  .modal-marginalia { grid-template-columns: 1fr; }
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
.meta {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

/* Design v3 modal and form polish. */
.modal {
  background: color-mix(in srgb, var(--surface-base) 72%, transparent);
}
.modal-card {
  background: var(--surface-elevated);
  border-color: var(--hairline);
  border-radius: var(--r-8);
  box-shadow: var(--shadow-4);
  font-family: var(--font-sans);
}
.modal-head,
.review-bar,
.modal-marginalia {
  border-color: var(--separator);
}
.kicker-mono,
.meta,
.form-row,
.chip {
  font-family: var(--font-sans);
  letter-spacing: 0;
  text-transform: none;
}
.modal-handle,
.modal-bio,
.form-row textarea {
  font-family: var(--font-sans);
}
.modal-handle {
  color: var(--text-primary);
}
.modal-bio,
.modal-persona {
  color: var(--text-secondary);
}
.form-row {
  color: var(--text-secondary);
  font-weight: 590;
}
.form-row input,
.form-row select,
.form-row textarea,
.regenerate-hint-input {
  background: var(--surface-elevated);
  border-color: var(--hairline);
  border-radius: var(--r-5);
  color: var(--text-primary);
  font-family: var(--font-sans);
}
.form-row input:focus,
.form-row select:focus,
.form-row textarea:focus,
.regenerate-hint-input:focus {
  box-shadow: 0 0 0 3px var(--focus-ring);
}
.chip {
  background: var(--surface-inset);
  border-color: var(--hairline);
  color: var(--text-secondary);
}
</style>
