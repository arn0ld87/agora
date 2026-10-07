<script setup lang="ts">
/**
 * Editor-Fenster für eine Persona (#1807, E7-F3) mit fünf Abschnitten: Identität,
 * Haltung und Ziele, Sprache und Ton, Aktivität, Bezug zum Graphen. Aufbau wie das
 * Einstellungsfenster: links die Abschnittsnavigation, rechts der Inhalt.
 *
 * Die Komponente speichert nicht selbst: sie meldet `save(profileInput)`, der
 * Aufrufer ruft `addEntry`/`updateEntry`. Die Herkunft (`origin`) wird nie
 * geändert; sie steht nur im Kopf und im Abschnitt „Bezug zum Graphen“.
 *
 * A11y: Dialog mit Beschriftung und Fokusfalle, Fokus auf dem ersten Feld beim
 * Öffnen und zurück zum Auslöser beim Schließen, Abschnittsnavigation als Tabliste
 * mit Pfeiltasten, Fehlertexte per `aria-describedby`, Fehlerzusammenfassung als
 * Alert (Fokus springt zum ersten Fehler), Statusmeldungen in einer Live-Region.
 */
import { computed, nextTick, reactive, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Badge from '@/components/ui/Badge.vue'
import type { PersonaOrigin, PersonaSetEntry, PersonaSetProfileInput } from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from './detailTestIds'
import EditorActivity from './editor/EditorActivity.vue'
import EditorGraph from './editor/EditorGraph.vue'
import EditorIdentity from './editor/EditorIdentity.vue'
import EditorLanguage from './editor/EditorLanguage.vue'
import EditorStance from './editor/EditorStance.vue'
import {
  EDITOR_SECTIONS,
  FIELD_SECTION,
  draftFromProfile,
  emptyDraft,
  fieldDomId,
  validateDraft,
  type DraftErrors,
  type EditorDraft,
  type EditorSectionId,
  type FieldMessages,
} from './editor/editorModel'
import './editor/editor.css'

const props = defineProps<{
  open: boolean
  /** `null` = neue Persona. */
  entry: PersonaSetEntry | null
  locked: boolean
  busy?: boolean
  error?: string | null
}>()
const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'save', profile: PersonaSetProfileInput): void
}>()
const { t } = useI18n()

const uid = useId()
const titleId = `${uid}-title`
const noteId = `${uid}-note`
const draft = reactive<EditorDraft>(emptyDraft())
const initialSnapshot = ref('')
const errors = ref<DraftErrors>({})
const section = ref<EditorSectionId>('identity')
const confirmDiscard = ref(false)
const root = ref<HTMLElement | null>(null)
const keepButton = ref<HTMLButtonElement | null>(null)
const tabButtons = ref<HTMLButtonElement[]>([])
let opener: HTMLElement | null = null

/** Neue Personas legt die View als `manual` an. */
const origin = computed<PersonaOrigin>(() => props.entry?.origin ?? 'manual')
const sourceEntityUuid = computed(() => props.entry?.source_entity_uuid ?? null)
const dirty = computed(() => JSON.stringify(draft) !== initialSnapshot.value)
const readonly = computed(() => props.locked)

const messages = computed<FieldMessages>(() => {
  const out: FieldMessages = {}
  for (const [field, err] of Object.entries(errors.value) as [keyof DraftErrors, NonNullable<DraftErrors[keyof DraftErrors]>][]) {
    out[field] = t(`views.personaSets.editor.errors.${err.key}`, err.params)
  }
  return out
})
const summary = computed(() =>
  (Object.keys(FIELD_SECTION) as (keyof typeof FIELD_SECTION)[])
    .filter((f) => errors.value[f])
    .map((f) => ({ field: f, label: t(`views.personaSets.editor.fields.${f}.label`), message: messages.value[f] ?? '' })),
)
const errorCountBySection = computed(() => {
  const counts: Record<EditorSectionId, number> = { identity: 0, stance: 0, language: 0, activity: 0, graph: 0 }
  for (const f of Object.keys(errors.value) as (keyof typeof FIELD_SECTION)[]) counts[FIELD_SECTION[f]] += 1
  return counts
})
const originSymbol = computed(() => ({ graph: '◇', manual: '✎', ai_draft: '✦', fallback: '⚠' })[origin.value])
const originVariant = computed(() => (origin.value === 'fallback' ? 'warn' : origin.value === 'ai_draft' ? 'info' : 'outline'))
const liveMessage = computed(() => (props.busy ? t('views.personaSets.editor.saving') : ''))

function focusField(field: keyof typeof FIELD_SECTION): void {
  section.value = FIELD_SECTION[field]
  void nextTick(() => document.getElementById(fieldDomId(uid, field))?.focus())
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      Object.assign(draft, props.entry ? draftFromProfile(props.entry.profile) : emptyDraft())
      initialSnapshot.value = JSON.stringify(draft)
      errors.value = {}
      section.value = 'identity'
      confirmDiscard.value = false
      await nextTick()
      document.getElementById(fieldDomId(uid, 'name'))?.focus()
    } else {
      const target = opener
      opener = null
      await nextTick()
      if (target?.isConnected) target.focus()
    }
  },
  { immediate: true },
)

function requestClose(): void {
  if (dirty.value && !props.locked) {
    confirmDiscard.value = true
    void nextTick(() => keepButton.value?.focus())
    return
  }
  emit('update:open', false)
}

function keepEditing(): void {
  confirmDiscard.value = false
  void nextTick(() => document.getElementById(fieldDomId(uid, 'name'))?.focus())
}

function discard(): void {
  confirmDiscard.value = false
  emit('update:open', false)
}

function submit(): void {
  if (props.locked || props.busy) return
  const result = validateDraft(draft)
  if (!result.ok) {
    errors.value = result.errors
    focusField(result.ordered[0])
    return
  }
  errors.value = {}
  emit('save', result.data)
}

function selectSection(id: EditorSectionId, focus = false): void {
  section.value = id
  if (focus) void nextTick(() => tabButtons.value[EDITOR_SECTIONS.indexOf(id)]?.focus())
}

function onTabKeydown(ev: KeyboardEvent): void {
  const last = EDITOR_SECTIONS.length - 1
  const i = EDITOR_SECTIONS.indexOf(section.value)
  let next: number | null = null
  if (ev.key === 'ArrowDown' || ev.key === 'ArrowRight') next = i === last ? 0 : i + 1
  else if (ev.key === 'ArrowUp' || ev.key === 'ArrowLeft') next = i === 0 ? last : i - 1
  else if (ev.key === 'Home') next = 0
  else if (ev.key === 'End') next = last
  if (next === null) return
  ev.preventDefault()
  selectSection(EDITOR_SECTIONS[next], true)
}

function onKeydown(ev: KeyboardEvent): void {
  if (ev.key === 'Escape') {
    ev.stopPropagation()
    if (confirmDiscard.value) keepEditing()
    else requestClose()
    return
  }
  if (ev.key !== 'Tab' || !root.value) return
  const items = [
    ...root.value.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, [tabindex]'),
  ].filter((el) => !el.hasAttribute('disabled') && el.getAttribute('tabindex') !== '-1')
  if (items.length === 0) return
  const first = items[0]
  const lastItem = items[items.length - 1]
  if (ev.shiftKey && (document.activeElement === first || document.activeElement === root.value)) {
    ev.preventDefault()
    lastItem.focus()
  } else if (!ev.shiftKey && document.activeElement === lastItem) {
    ev.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <div v-if="open" class="pe-backdrop">
    <div
      ref="root"
      class="pe"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-labelledby="titleId"
      :aria-describedby="noteId"
      :data-testid="Id.editor"
      @keydown="onKeydown"
    >
      <header class="pe__head">
        <h2 :id="titleId" class="pe__title">
          {{ entry ? t('views.personaSets.editor.titleEdit', { name: entry.profile.name }) : t('views.personaSets.editor.titleNew') }}
        </h2>
        <div :id="noteId" class="pe__origin">
          <Badge :variant="originVariant" :data-testid="Id.editorOrigin" :data-origin="origin">
            <span aria-hidden="true">{{ originSymbol }}</span>
            {{ t(`views.personaSets.detail.origin.${origin}`) }}
          </Badge>
          <span class="pe__origin-note" :data-testid="Id.editorOriginNote">{{ t(`views.personaSets.editor.originNote.${origin}`) }}</span>
        </div>
        <p v-if="locked" class="pe__locked" :data-testid="Id.editorLockedReason">
          {{ t('views.personaSets.editor.locked') }}
        </p>
      </header>

      <form class="pe__form" novalidate @submit.prevent="submit">
        <div
          v-if="summary.length > 0"
          class="pe__summary"
          role="alert"
          :data-testid="Id.editorSummary"
        >
          <p class="pe__summary-title">{{ t('views.personaSets.editor.summaryTitle', { n: summary.length }) }}</p>
          <ul>
            <li v-for="item in summary" :key="item.field">
              <button type="button" class="pe__summary-link" :data-testid="Id.editorSummaryItem" @click="focusField(item.field)">
                {{ item.label }}: {{ item.message }}
              </button>
            </li>
          </ul>
        </div>

        <div class="pe__body">
          <nav class="pe__nav" :aria-label="t('views.personaSets.editor.navLabel')">
            <div role="tablist" aria-orientation="vertical" class="pe__tabs" @keydown="onTabKeydown">
              <button
                v-for="(id, i) in EDITOR_SECTIONS"
                :id="`${uid}-tab-${id}`"
                :key="id"
                :ref="(el) => { if (el) tabButtons[i] = el as HTMLButtonElement }"
                type="button"
                role="tab"
                class="pe__tab"
                :class="{ 'pe__tab--active': section === id }"
                :aria-selected="section === id"
                :aria-controls="`${uid}-panel`"
                :tabindex="section === id ? 0 : -1"
                :data-testid="Id.editorTab"
                :data-section="id"
                @click="selectSection(id)"
              >
                <span>{{ t(`views.personaSets.editor.sections.${id}.label`) }}</span>
                <span v-if="errorCountBySection[id] > 0" class="pe__tab-err">
                  <span aria-hidden="true">⚠ {{ errorCountBySection[id] }}</span>
                  <span class="pe-sr">{{ t('views.personaSets.editor.sectionErrors', { n: errorCountBySection[id] }) }}</span>
                </span>
              </button>
            </div>
          </nav>

          <div
            :id="`${uid}-panel`"
            class="pe__panel"
            role="tabpanel"
            :aria-labelledby="`${uid}-tab-${section}`"
            :data-testid="Id.editorPanel"
            :data-section="section"
          >
            <EditorIdentity v-if="section === 'identity'" v-model="draft" :uid="uid" :errors="messages" :readonly="readonly" />
            <EditorStance v-else-if="section === 'stance'" v-model="draft" :uid="uid" :errors="messages" :readonly="readonly" />
            <EditorLanguage v-else-if="section === 'language'" v-model="draft" :uid="uid" :errors="messages" :readonly="readonly" />
            <EditorActivity v-else-if="section === 'activity'" v-model="draft" :uid="uid" :errors="messages" :readonly="readonly" />
            <EditorGraph
              v-else
              v-model="draft"
              :uid="uid"
              :errors="messages"
              :readonly="readonly"
              :origin="origin"
              :source-entity-uuid="sourceEntityUuid"
            />
          </div>
        </div>

        <p v-if="error" class="pe__error" role="alert" :data-testid="Id.editorError">
          <span aria-hidden="true">⚠ </span>{{ error }}
        </p>

        <div v-if="confirmDiscard" class="pe__confirm" role="alert" :data-testid="Id.editorConfirm">
          <p>{{ t('views.personaSets.editor.confirm.text') }}</p>
          <div class="pe__actions">
            <button ref="keepButton" type="button" :data-testid="Id.editorConfirmKeep" @click="keepEditing">
              {{ t('views.personaSets.editor.confirm.keep') }}
            </button>
            <button type="button" :data-testid="Id.editorConfirmDiscard" @click="discard">
              {{ t('views.personaSets.editor.confirm.discard') }}
            </button>
          </div>
        </div>

        <footer class="pe__foot">
          <span class="pe-sr" role="status" aria-live="polite" :data-testid="Id.editorLive">{{ liveMessage }}</span>
          <p v-if="dirty && !locked" class="pe__dirty">{{ t('views.personaSets.editor.unsaved') }}</p>
          <div class="pe__actions">
            <button type="submit" class="pe__primary" :disabled="locked || busy" :data-testid="Id.editorSave">
              {{ busy ? t('views.personaSets.editor.saving') : t('views.personaSets.editor.save') }}
            </button>
            <button type="button" :data-testid="Id.editorCancel" @click="requestClose">
              {{ locked ? t('views.personaSets.editor.close') : t('views.personaSets.editor.cancel') }}
            </button>
          </div>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.pe-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: var(--scrim, rgb(0 0 0 / 0.4));
  z-index: 200;
}

.pe {
  display: flex;
  flex-direction: column;
  width: min(900px, calc(100vw - 32px));
  height: min(680px, calc(100dvh - 32px));
  background: var(--s2);
  color: var(--fg);
  border-radius: var(--ag-r-16);
  box-shadow: var(--shadow-dlg);
  overflow: hidden;
  font-family: var(--ag-font-sans);
}

.pe:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: -2px;
}

.pe__head {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 26px 10px;
}

.pe__title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
}

.pe__origin {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--fg2);
}

.pe__locked {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  font-size: 13px;
}

.pe__form {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.pe__summary {
  flex: none;
  margin: 0 26px 8px;
  padding: 10px 14px;
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  font-size: 13px;
}

.pe__summary-title {
  margin: 0 0 4px;
  font-weight: 650;
}

.pe__summary ul {
  margin: 0;
  padding-left: 18px;
}

.pe__summary-link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--err);
  font: inherit;
  text-align: left;
  text-decoration: underline;
  cursor: pointer;
}

.pe__body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.pe__nav {
  width: 220px;
  flex: none;
  padding: 10px;
  background: var(--s1);
  overflow-y: auto;
}

.pe__tabs {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pe__tab {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  text-align: left;
  cursor: pointer;
}

.pe__tab:hover {
  background: var(--s3);
}

.pe__tab--active,
.pe__tab--active:hover {
  background: var(--acc-soft);
  font-weight: 600;
}

.pe__tab:focus-visible,
.pe__summary-link:focus-visible,
.pe__actions button:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.pe__tab-err {
  color: var(--err);
  font-size: 12px;
}

.pe__panel {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 8px 26px 16px;
}

.pe__error {
  flex: none;
  margin: 0 26px 8px;
  color: var(--err);
  font-size: 13px;
}

.pe__confirm {
  flex: none;
  margin: 0 26px 8px;
  padding: 10px 14px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  font-size: 13px;
}

.pe__confirm p {
  margin: 0 0 8px;
}

.pe__foot {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 26px 16px;
  border-top: 1px solid var(--line);
}

.pe__dirty {
  margin: 0;
  font-size: 12.5px;
  color: var(--fg3);
}

.pe__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.pe__actions button {
  padding: 7px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s1);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  cursor: pointer;
}

.pe__actions button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.pe__actions .pe__primary {
  background: var(--acc);
  border-color: var(--acc);
  color: var(--on-acc);
}

@media (max-width: 767px) {
  .pe {
    width: calc(100vw - 16px);
    height: calc(100dvh - 16px);
  }

  .pe__body {
    flex-direction: column;
  }

  .pe__nav {
    width: auto;
    padding: 6px 10px;
    overflow-x: auto;
  }

  .pe__tabs {
    flex-direction: row;
  }

  .pe__tab {
    white-space: nowrap;
  }

  .pe__panel,
  .pe__head,
  .pe__foot {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
