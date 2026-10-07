<script setup lang="ts">
/**
 * Platzhalter-Editor für eine Persona (#1807, E7-F2): nur Name und Benutzername.
 * Der volle Editor mit fünf Abschnitten ersetzt den Inhalt dieser Datei, die
 * Schnittstelle (Props/Emits) bleibt. Die Komponente speichert nicht selbst:
 * sie meldet `save(profileInput)`, der Aufrufer ruft `addEntry`/`updateEntry`.
 *
 * A11y: Dialog mit Beschriftung, Fokus auf das erste Feld beim Öffnen, Escape
 * schließt, Tab bleibt im Dialog, der Fokus kehrt zum auslösenden Element zurück.
 */
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PersonaSetProfileInputSchema,
  type PersonaSetEntry,
  type PersonaSetProfileInput,
} from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from './detailTestIds'

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

const name = ref('')
const username = ref('')
const validation = ref<string | null>(null)
const root = ref<HTMLElement | null>(null)
const nameField = ref<HTMLInputElement | null>(null)
let opener: HTMLElement | null = null

watch(
  () => props.open,
  async (open) => {
    if (open) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      name.value = props.entry?.profile.name ?? ''
      username.value = props.entry?.profile.username ?? ''
      validation.value = null
      await nextTick()
      nameField.value?.focus()
    } else {
      const target = opener
      opener = null
      await nextTick()
      if (target?.isConnected) target.focus()
    }
  },
  { immediate: true },
)

function close(): void {
  emit('update:open', false)
}

function submit(): void {
  if (props.locked) return
  const base = props.entry?.profile ?? {}
  const parsed = PersonaSetProfileInputSchema.safeParse({
    ...base,
    name: name.value.trim(),
    username: username.value.trim(),
  })
  if (!parsed.success) {
    validation.value = t('views.personaSets.detail.editor.invalid')
    return
  }
  validation.value = null
  emit('save', parsed.data)
}

function onKeydown(ev: KeyboardEvent): void {
  if (ev.key === 'Escape') {
    ev.stopPropagation()
    close()
    return
  }
  if (ev.key !== 'Tab' || !root.value) return
  const items = [...root.value.querySelectorAll<HTMLElement>('input, button, textarea, select')].filter((el) => !el.hasAttribute('disabled'))
  if (items.length === 0) return
  const first = items[0]
  const last = items[items.length - 1]
  if (ev.shiftKey && document.activeElement === first) {
    ev.preventDefault()
    last.focus()
  } else if (!ev.shiftKey && document.activeElement === last) {
    ev.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <div v-if="open" class="pdlg__backdrop">
    <div
      ref="root"
      class="pdlg"
      role="dialog"
      aria-modal="true"
      aria-labelledby="persona-editor-title"
      :data-testid="Id.editor"
      @keydown="onKeydown"
    >
      <h2 id="persona-editor-title">
        {{ entry ? t('views.personaSets.detail.editor.titleEdit') : t('views.personaSets.detail.editor.titleNew') }}
      </h2>
      <p v-if="locked" role="status" class="pdlg__locked">{{ t('views.personaSets.detail.editor.lockedHint') }}</p>
      <form @submit.prevent="submit">
        <label class="pdlg__field">
          <span>{{ t('views.personaSets.detail.editor.name') }}</span>
          <input ref="nameField" v-model="name" type="text" maxlength="120" required :disabled="locked" :data-testid="Id.editorName" />
        </label>
        <label class="pdlg__field">
          <span>{{ t('views.personaSets.detail.editor.username') }}</span>
          <input v-model="username" type="text" maxlength="64" required :disabled="locked" :data-testid="Id.editorUsername" />
        </label>
        <p v-if="validation || error" role="alert" :data-testid="Id.editorError">{{ validation ?? error }}</p>
        <div class="pdlg__actions">
          <button type="submit" :disabled="locked || busy" :data-testid="Id.editorSave">
            {{ t('views.personaSets.detail.editor.save') }}
          </button>
          <button type="button" :data-testid="Id.editorCancel" @click="close">
            {{ t('views.personaSets.detail.editor.cancel') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.pdlg__backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgb(0 0 0 / 0.4);
  z-index: 50;
}
.pdlg {
  min-width: min(480px, 92vw);
  padding: var(--sp-6, 24px);
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline-strong, var(--hairline));
  border-radius: var(--r-7, var(--r-3));
  box-shadow: var(--shadow-2, var(--shadow-1));
}
.pdlg__field { display: flex; flex-direction: column; gap: var(--sp-1, 4px); margin-bottom: var(--sp-3, 12px); }
.pdlg__actions { display: flex; gap: var(--sp-2, 8px); justify-content: flex-end; }
.pdlg__locked { color: var(--text-secondary, var(--fg-muted)); }
</style>
