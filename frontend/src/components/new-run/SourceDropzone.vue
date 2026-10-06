<script setup lang="ts">
/**
 * SourceDropzone — Dateiablage des Startdialogs (Logik aus HeroNewRun):
 * .pdf/.md/.txt/.markdown, Anhängen statt Ersetzen, Textsorte je Datei
 * (positionsgleich zu `files`, Issue #1240).
 *
 * Die Ablagefläche ist ein echter Button (Tastatur: Enter/Leertaste öffnet die
 * Dateiauswahl); Ziehen und Ablegen ist die Zugabe, nicht der einzige Weg.
 */
import { ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { DocumentRoleSchema, type DocumentRole } from '@/contracts/documentRoleContract'

const ALLOWED_SOURCE_EXTENSIONS = ['.pdf', '.md', '.txt', '.markdown']

const { t } = useI18n()
const files = defineModel<File[]>('files', { required: true })
const documentRoles = defineModel<DocumentRole[]>('documentRoles', { required: true })
const props = defineProps<{ disabled?: boolean; describedby?: string }>()
const emit = defineEmits<{ (e: 'rejected'): void; (e: 'accepted'): void }>()

const ROLES = DocumentRoleSchema.options
const input = ref<HTMLInputElement | null>(null)
const over = ref(false)
const listId = useId()

function accept(list: FileList): void {
  const accepted = Array.from(list).filter((f) =>
    ALLOWED_SOURCE_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)),
  )
  files.value = [...files.value, ...accepted]
  documentRoles.value = [...documentRoles.value, ...accepted.map((): DocumentRole => 'domain_fact')]
  if (accepted.length === 0 && list.length > 0) emit('rejected')
  else emit('accepted')
}

function onPick(event: Event): void {
  const el = event.target as HTMLInputElement
  if (el.files) accept(el.files)
  el.value = ''
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  over.value = false
  if (props.disabled || !event.dataTransfer?.files) return
  accept(event.dataTransfer.files)
}

function remove(index: number): void {
  files.value = files.value.filter((_f, i) => i !== index)
  documentRoles.value = documentRoles.value.filter((_r, i) => i !== index)
}

function onRole(index: number, event: Event): void {
  const parsed = DocumentRoleSchema.safeParse((event.target as HTMLSelectElement).value)
  if (!parsed.success) return
  const next = [...documentRoles.value]
  next[index] = parsed.data
  documentRoles.value = next
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <div class="nr-drop">
    <button
      type="button"
      class="nr-drop__area"
      :class="{ 'nr-drop__area--over': over }"
      :disabled="disabled"
      :aria-describedby="describedby"
      data-testid="new-run-drop"
      @click="input?.click()"
      @dragover.prevent="over = true"
      @dragleave="over = false"
      @drop="onDrop"
    >
      <span class="nr-drop__title">{{ t('views.newRun.source.dropHint') }}</span>
      <span class="nr-drop__formats">{{ ALLOWED_SOURCE_EXTENSIONS.join('  ·  ') }}</span>
    </button>
    <input
      ref="input"
      type="file"
      class="nr-drop__input"
      tabindex="-1"
      aria-hidden="true"
      :accept="ALLOWED_SOURCE_EXTENSIONS.join(',')"
      multiple
      data-testid="new-run-file-input"
      @change="onPick"
    />
    <ul v-if="files.length > 0" :id="listId" class="nr-drop__files" :aria-label="t('views.newRun.source.fileList')">
      <li v-for="(f, i) in files" :key="`${f.name}-${i}`" class="nr-drop__file">
        <span class="nr-drop__name">{{ f.name }}</span>
        <select
          class="nr-drop__role"
          :aria-label="`${t('dashboard.hero.documentRoleLabel')}: ${f.name}`"
          :value="documentRoles[i] ?? 'domain_fact'"
          :disabled="disabled"
          @change="onRole(i, $event)"
        >
          <option v-for="role in ROLES" :key="role" :value="role">
            {{ t(`dashboard.hero.documentRoles.${role}`) }}
          </option>
        </select>
        <span class="nr-drop__size">{{ formatBytes(f.size) }}</span>
        <button
          type="button"
          class="nr-drop__remove"
          :disabled="disabled"
          :aria-label="`${t('common.delete')}: ${f.name}`"
          @click="remove(i)"
        >
          <span aria-hidden="true">✕</span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.nr-drop {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.nr-drop__area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 18px;
  border: 1px dashed var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg2);
  font: inherit;
  cursor: pointer;
}

.nr-drop__area:hover:not(:disabled),
.nr-drop__area--over {
  background: var(--s3);
}

.nr-drop__area:focus-visible,
.nr-drop__role:focus-visible,
.nr-drop__remove:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.nr-drop__area:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.nr-drop__title {
  color: var(--fg);
  font-size: 13.5px;
}

.nr-drop__formats {
  font-size: 12px;
}

.nr-drop__input {
  display: none;
}

.nr-drop__files {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nr-drop__file {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 13px;
}

.nr-drop__name {
  flex: 1 1 140px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.nr-drop__role {
  min-width: 0;
  max-width: 100%;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 12.5px;
}

.nr-drop__size {
  color: var(--fg2);
  font-size: 12px;
}

.nr-drop__remove {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  cursor: pointer;
}

.nr-drop__remove:hover:not(:disabled) {
  background: var(--s3);
}
</style>
