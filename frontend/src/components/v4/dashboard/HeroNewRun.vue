<script setup lang="ts">
/**
 * HeroNewRun — primärer Aktions-Block des Dashboards.
 *
 * Workbench-These: ruhige Card, drei Zonen (Quelle | Modell+Sprache | Aktion),
 * Akzent-Aktion rechts. Keine Glows, keine Marketing-Kicker.
 *
 * Spiegelt den bestehenden Home.vue-Flow (setPendingUpload → /process/new),
 * aber ohne Hero-Headline-Cluster und ohne LandingPage-Layout.
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import IconPlus from '../shell/icons/IconPlus.vue'
import { getAvailableModels } from '../../../api/simulation'
import { setPendingUpload } from '../../../store/pendingUpload'
import { STORAGE_CUSTOM_MODEL, STORAGE_LANG, STORAGE_MODEL } from '../../../composables/useEnvForm'

interface ModelOption {
  value: string
  label: string
}

const { t } = useI18n()
const router = useRouter()

const ALLOWED = ['.pdf', '.md', '.txt', '.markdown']

const files = ref<File[]>([])
const isDragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const errorMsg = ref('')

const presetModels = ref<ModelOption[]>([])
const ollamaModels = ref<ModelOption[]>([])
const defaultModel = ref('')
const ollamaReachable = ref(false)
const loadingStatus = ref(true)

function readLocal(key: string): string | null {
  try {
    if (typeof window === 'undefined') return null
    const ls = window.localStorage
    if (!ls || typeof ls.getItem !== 'function') return null
    return ls.getItem(key)
  } catch {
    return null
  }
}

function writeLocal(key: string, value: string): void {
  try {
    if (typeof window === 'undefined') return
    const ls = window.localStorage
    if (!ls || typeof ls.setItem !== 'function') return
    ls.setItem(key, value)
  } catch { /* swallow */ }
}

function removeLocal(key: string): void {
  try {
    if (typeof window === 'undefined') return
    const ls = window.localStorage
    if (!ls || typeof ls.removeItem !== 'function') return
    ls.removeItem(key)
  } catch { /* swallow */ }
}

const modelOption = ref<string>(readLocal(STORAGE_MODEL) || 'default')
const language = ref<string>(readLocal(STORAGE_LANG) || 'de')

const modelOptions = computed<ModelOption[]>(() => {
  const opts: ModelOption[] = [
    { value: 'default', label: `${t('dashboard.hero.modelDefault')} — ${defaultModel.value || '?'}` },
  ]
  for (const p of presetModels.value) opts.push(p)
  for (const m of ollamaModels.value) {
    if (presetModels.value.some(p => p.value === m.value)) continue
    opts.push({ value: m.value, label: `${m.label} (Ollama)` })
  }
  return opts
})

const canSubmit = computed(() => files.value.length > 0 && !loadingStatus.value)

async function loadStatus() {
  loadingStatus.value = true
  try {
    const res = await getAvailableModels()
    const data = (res as { data?: Record<string, unknown>; success?: boolean })?.data ?? null
    if (data) {
      const presets = (data['presets'] as Array<Record<string, unknown>>) ?? []
      const ollama = (data['ollama'] as Array<Record<string, unknown>>) ?? []
      presetModels.value = presets.map(p => ({
        value: String(p['name'] ?? ''),
        label: String(p['label'] ?? p['name'] ?? ''),
      })).filter(o => !!o.value)
      ollamaModels.value = ollama.map(p => ({
        value: String(p['name'] ?? ''),
        label: String(p['label'] ?? p['name'] ?? ''),
      })).filter(o => !!o.value)
      defaultModel.value = String(data['current_default'] ?? '')
      ollamaReachable.value = !!data['ollama_reachable']
    }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loadingStatus.value = false
  }
}

function filterAllowed(list: FileList | File[]): File[] {
  return Array.from(list).filter(f => {
    const lower = f.name.toLowerCase()
    return ALLOWED.some(ext => lower.endsWith(ext))
  })
}

function onPickClick() {
  fileInput.value?.click()
}

function onPickKey(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    onPickClick()
  }
}

function onFiles(e: Event) {
  const t = e.target as HTMLInputElement
  if (!t.files) return
  const accepted = filterAllowed(t.files)
  files.value = accepted
  if (accepted.length === 0 && t.files.length > 0) {
    errorMsg.value = t.value
      ? ''
      : ''
    errorMsg.value = ''
  }
  t.value = ''
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  if (!e.dataTransfer?.files) return
  files.value = filterAllowed(e.dataTransfer.files)
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function removeFile(i: number) {
  files.value.splice(i, 1)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function startSimulation() {
  if (!canSubmit.value) return
  try {
    writeLocal(STORAGE_MODEL, modelOption.value)
    writeLocal(STORAGE_LANG, language.value)
    removeLocal(STORAGE_CUSTOM_MODEL)
    setPendingUpload(files.value, '')
    router.push({ name: 'Process', params: { projectId: 'new' } })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => void loadStatus())
</script>

<template>
  <Card :title="$t('dashboard.hero.title')" :subtitle="$t('dashboard.hero.subtitle')">
    <template #right>
      <Badge
        v-if="!loadingStatus"
        :tone="ollamaReachable ? 'green' : 'gray'"
      >
        {{ ollamaReachable ? $t('dashboard.system.statusReachable') : $t('dashboard.system.statusIdle') }}
      </Badge>
    </template>

    <div class="hero-grid">
      <!-- Zone 1: Quelle (Drop / Picker) -->
      <div class="hero-zone hero-source">
        <label class="hero-label">{{ $t('dashboard.hero.sourceLabel') }}</label>
        <div
          class="hero-drop"
          :class="{ 'hero-drop--over': isDragOver, 'hero-drop--filled': files.length > 0 }"
          role="button"
          tabindex="0"
          @click="onPickClick"
          @keydown="onPickKey"
          @drop="onDrop"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
        >
          <template v-if="files.length === 0">
            <IconPlus :size="18" :stroke="1.6" class="hero-drop__icon" />
            <span class="hero-drop__title">{{ $t('dashboard.hero.dropHint') }}</span>
            <span class="hero-drop__formats">{{ ALLOWED.join('  ·  ') }}</span>
          </template>
          <template v-else>
            <ul class="hero-files">
              <li v-for="(f, i) in files" :key="`${f.name}-${i}`" class="hero-file">
                <span class="hero-file__name">{{ f.name }}</span>
                <span class="hero-file__size">{{ formatBytes(f.size) }}</span>
                <button
                  type="button"
                  class="hero-file__remove"
                  :aria-label="$t('common.delete')"
                  @click.stop="removeFile(i)"
                >
                  ✕
                </button>
              </li>
            </ul>
          </template>
        </div>
        <input
          ref="fileInput"
          type="file"
          class="hero-input-hidden"
          :accept="ALLOWED.join(',')"
          multiple
          @change="onFiles"
        />
      </div>

      <!-- Zone 2: Model + Sprache -->
      <div class="hero-zone hero-config">
        <div class="hero-field">
          <label class="hero-label" for="hero-model">{{ $t('dashboard.hero.modelLabel') }}</label>
          <select id="hero-model" v-model="modelOption" class="hero-select">
            <option v-for="opt in modelOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-lang">{{ $t('dashboard.hero.languageLabel') }}</label>
          <select id="hero-lang" v-model="language" class="hero-select">
            <option value="de">Deutsch</option>
            <option value="en">English</option>
          </select>
        </div>
      </div>

      <!-- Zone 3: Aktion -->
      <div class="hero-zone hero-action">
        <button
          type="button"
          class="hero-cta"
          :disabled="!canSubmit"
          :aria-disabled="!canSubmit"
          @click="startSimulation"
        >
          {{ $t('dashboard.hero.startCta') }}
        </button>
        <p v-if="!canSubmit && !loadingStatus" class="hero-hint">
          {{ $t('dashboard.hero.disabledHint') }}
        </p>
        <p v-if="errorMsg" class="hero-error">{{ errorMsg }}</p>
      </div>
    </div>
  </Card>
</template>

<style scoped>
.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 0.9fr);
  gap: 24px;
  align-items: stretch;
}

.hero-zone {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.hero-label {
  font-family: var(--font-sans);
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

/* Drop-Zone */
.hero-drop {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px dashed var(--hairline-strong);
  border-radius: var(--r-5, 10px);
  padding: 22px;
  background: var(--surface-inset, #f2f2f7);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 80ms ease, border-color 80ms ease;
  min-height: 132px;
}

.hero-drop:hover {
  background: var(--surface-hover);
}

.hero-drop:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.hero-drop--over {
  background: var(--accent-tint-bg);
  border-color: var(--accent);
  color: var(--accent-tint-text);
}

.hero-drop--filled {
  align-items: stretch;
  justify-content: flex-start;
  padding: 12px;
  background: var(--surface-elevated);
  border-style: solid;
  border-color: var(--hairline);
}

.hero-drop__icon {
  color: var(--text-tertiary);
}

.hero-drop__title {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.hero-drop__formats {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
}

.hero-files {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.hero-file {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 12px;
  padding: 6px 8px;
  border-radius: var(--r-4, 8px);
  font-family: var(--font-sans);
  font-size: 13px;
}

.hero-file:hover {
  background: var(--surface-hover);
}

.hero-file__name {
  font-family: var(--font-mono);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero-file__size {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-tertiary);
}

.hero-file__remove {
  background: transparent;
  border: 0;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: var(--r-3, 6px);
}

.hero-file__remove:hover {
  background: var(--surface-pressed);
  color: var(--text-secondary);
}

.hero-input-hidden {
  display: none;
}

/* Config */
.hero-config {
  justify-content: center;
}

.hero-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero-select {
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 9px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
  appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, var(--text-tertiary) 50%),
                    linear-gradient(135deg, var(--text-tertiary) 50%, transparent 50%);
  background-position: calc(100% - 14px) 50%, calc(100% - 9px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
  padding-right: 28px;
}

.hero-select:hover {
  border-color: var(--hairline-strong);
}

.hero-select:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

/* Aktion */
.hero-action {
  justify-content: center;
  align-items: stretch;
}

.hero-cta {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.005em;
  background: var(--accent);
  color: var(--text-on-accent);
  border: 0;
  border-radius: var(--r-5, 10px);
  padding: 12px 18px;
  cursor: pointer;
  transition: background 80ms ease;
}

.hero-cta:hover:not(:disabled) {
  background: var(--accent-hover);
}

.hero-cta:active:not(:disabled) {
  background: var(--accent-pressed);
}

.hero-cta:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.hero-cta:disabled {
  background: var(--gray-4, #d1d1d6);
  color: var(--text-quaternary);
  cursor: not-allowed;
}

.hero-hint {
  margin: 8px 0 0;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
}

.hero-error {
  margin: 8px 0 0;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--status-red);
  text-align: center;
}

@media (max-width: 900px) {
  .hero-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero-drop,
  .hero-cta,
  .hero-select,
  .hero-file__remove {
    transition: none;
  }
}
</style>
