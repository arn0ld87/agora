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
import ModelPicker from '../forms/ModelPicker.vue'
import IconPlus from '../shell/icons/IconPlus.vue'
import { fetchLlmProfiles } from '../../../api/llmProfiles'
import { setPendingUpload } from '../../../store/pendingUpload'
import { STORAGE_LANG, STORAGE_MODEL } from '../../../composables/useEnvForm'
import type { LlmProfile } from '../../../contracts/llmProfileContract'
import { StageLLMRouteSchema, type StageLLMRoute } from '../../../contracts/llmRoutingContract'

const { t } = useI18n()
const router = useRouter()

const ALLOWED = ['.pdf', '.md', '.txt', '.markdown']

const files = ref<File[]>([])
const isDragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const errorMsg = ref('')

const llmProfiles = ref<LlmProfile[]>([])

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

/**
 * Slice A2 (2026-05-17): Modell-Auswahl auf den projektweiten ModelPicker
 * konsolidiert. Hybrid-Mode:
 *   - Profile-Dropdown (links): LLM-Profile aus fetchLlmProfiles. Wenn gewählt,
 *     gewinnt das Profile — Provider/Modell/Temperatur kommen aus dem Profile.
 *   - ModelPicker (rechts, sichtbar wenn kein Profile aktiv): Direkt-Auswahl
 *     aus den unter /settings/llm-providers hinterlegten Providern.
 *
 * Persistenz: `agora.hero.profileId`, `agora.hero.route` (Zod-validiert).
 * MainView.handleNewProject liest weiterhin den klassischen STORAGE_MODEL-Key
 * via `storedEffectiveModel()` — wir spiegeln `route.model` dorthin, damit der
 * bestehende Sim-Start-Flow (Backend resolved Provider via SecretResolver,
 * vgl. PR #499) ohne Touch in MainView durchgeht.
 */
const STORAGE_HERO_PROFILE_ID = 'agora.hero.profileId'
const STORAGE_HERO_ROUTE = 'agora.hero.route'

function loadStoredRoute(): StageLLMRoute | null {
  const raw = readLocal(STORAGE_HERO_ROUTE)
  if (!raw) return null
  try {
    const parsed = StageLLMRouteSchema.safeParse(JSON.parse(raw))
    if (!parsed.success) return null
    if (!parsed.data.provider_id || !parsed.data.model) return null
    return parsed.data
  } catch {
    return null
  }
}

const selectedProfileId = ref<string | null>(readLocal(STORAGE_HERO_PROFILE_ID))
const selectedRoute = ref<StageLLMRoute | null>(loadStoredRoute())
const language = ref<string>(readLocal(STORAGE_LANG) || 'de')
const simulationRequirement = ref('')

const NUM_AGENTS_MIN = 10
const NUM_AGENTS_FLOOR = 30
const NUM_AGENTS_MAX = 100
const NUM_ROUNDS_MIN = 3
const NUM_ROUNDS_DEFAULT = 10
const NUM_ROUNDS_MAX = 30

const numAgents = ref<number>(NUM_AGENTS_FLOOR)
const numRounds = ref<number>(NUM_ROUNDS_DEFAULT)

const showAgentsWarning = computed<boolean>(
  () => numAgents.value >= NUM_AGENTS_MIN && numAgents.value < NUM_AGENTS_FLOOR,
)

const profileOptions = computed(() => {
  return llmProfiles.value.map(p => ({
    value: p.id,
    label: `${p.name} — ${p.model_name}${p.is_default ? ` (${t('dashboard.hero.profileDefault')})` : ''}`,
  }))
})

const canSubmit = computed(
  () => files.value.length > 0 && simulationRequirement.value.trim() !== '',
)

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

function applyAcceptedFiles(rawFiles: FileList): void {
  const accepted = filterAllowed(rawFiles)
  files.value = accepted
  if (accepted.length === 0 && rawFiles.length > 0) {
    errorMsg.value = t('errors.fileTypeNotAllowed')
  } else {
    errorMsg.value = ''
  }
}

function onFiles(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  applyAcceptedFiles(input.files)
  input.value = ''
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragOver.value = false
  if (!e.dataTransfer?.files) return
  applyAcceptedFiles(e.dataTransfer.files)
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

function onPickRoute(route: StageLLMRoute | null) {
  selectedRoute.value = route
  if (route?.provider_id && route?.model) {
    writeLocal(STORAGE_HERO_ROUTE, JSON.stringify(route))
  } else {
    removeLocal(STORAGE_HERO_ROUTE)
  }
}

function onPickProfile(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  selectedProfileId.value = value || null
  if (value) {
    writeLocal(STORAGE_HERO_PROFILE_ID, value)
  } else {
    removeLocal(STORAGE_HERO_PROFILE_ID)
  }
}

async function startSimulation() {
  if (!canSubmit.value) return
  try {
    writeLocal(STORAGE_LANG, language.value)
    const profileId = selectedProfileId.value || null
    // Wenn ein Profile aktiv ist, gewinnt es — direct-route ignorieren und
    // den STORAGE_MODEL-Key auf "default" zurücksetzen, damit MainView nicht
    // versehentlich einen stale Override mitsendet.
    if (profileId) {
      writeLocal(STORAGE_MODEL, 'default')
    } else if (selectedRoute.value?.model) {
      writeLocal(STORAGE_MODEL, selectedRoute.value.model)
    } else {
      writeLocal(STORAGE_MODEL, 'default')
    }
    setPendingUpload(
      files.value,
      simulationRequirement.value.trim(),
      profileId,
      numAgents.value,
      numRounds.value,
    )
    router.push({ name: 'Process', params: { projectId: 'new' } })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => {
  fetchLlmProfiles()
    .then(profiles => { llmProfiles.value = profiles })
    .catch(() => { /* Fallback: Profile-Picker bleibt leer, ModelPicker greift */ })
})
</script>

<template>
  <Card :title="$t('dashboard.hero.title')" :subtitle="$t('dashboard.hero.subtitle')">
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
          <label class="hero-label" for="hero-profile">
            {{ $t('dashboard.hero.profileLabel') }}
          </label>
          <select
            id="hero-profile"
            class="hero-select"
            :value="selectedProfileId ?? ''"
            @change="onPickProfile"
          >
            <option value="">
              {{ $t('dashboard.hero.profileNone') }}
            </option>
            <option v-for="opt in profileOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </div>
        <div v-if="!selectedProfileId" class="hero-field">
          <label class="hero-label">{{ $t('dashboard.hero.modelLabel') }}</label>
          <ModelPicker
            :model-value="selectedRoute"
            :placeholder="$t('dashboard.hero.modelPlaceholder')"
            @update:model-value="onPickRoute"
          />
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-lang">{{ $t('dashboard.hero.languageLabel') }}</label>
          <select id="hero-lang" v-model="language" class="hero-select">
            <option value="de">Deutsch</option>
            <option value="en">English</option>
          </select>
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-num-agents">
            {{ $t('dashboard.hero.numAgentsLabel') }}
            <span class="hero-slider-value">{{ numAgents }}</span>
          </label>
          <input
            id="hero-num-agents"
            v-model.number="numAgents"
            type="range"
            :min="NUM_AGENTS_MIN"
            :max="NUM_AGENTS_MAX"
            step="1"
            class="hero-slider"
            :aria-valuenow="numAgents"
            :aria-valuemin="NUM_AGENTS_MIN"
            :aria-valuemax="NUM_AGENTS_MAX"
          />
          <div v-if="showAgentsWarning" class="hero-warning" role="alert">
            <span class="hero-warning__icon" aria-hidden="true">&#9888;</span>
            {{ $t('dashboard.hero.numAgentsWarning') }}
          </div>
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-num-rounds">
            {{ $t('dashboard.hero.numRoundsLabel') }}
            <span class="hero-slider-value">{{ numRounds }}</span>
          </label>
          <input
            id="hero-num-rounds"
            v-model.number="numRounds"
            type="range"
            :min="NUM_ROUNDS_MIN"
            :max="NUM_ROUNDS_MAX"
            step="1"
            class="hero-slider"
            :aria-valuenow="numRounds"
            :aria-valuemin="NUM_ROUNDS_MIN"
            :aria-valuemax="NUM_ROUNDS_MAX"
          />
        </div>
        <div class="hero-field hero-field--full">
          <label class="hero-label" for="hero-requirement">
            {{ $t('dashboard.hero.requirementLabel') }}
            <span class="hero-required">*</span>
          </label>
          <textarea
            id="hero-requirement"
            v-model="simulationRequirement"
            class="hero-textarea"
            :placeholder="$t('dashboard.hero.requirementPlaceholder')"
            rows="3"
          />
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
        <p v-if="!canSubmit" class="hero-hint">
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

.hero-field--full {
  width: 100%;
}

/* Slider */
.hero-slider {
  width: 100%;
  accent-color: var(--accent);
  cursor: pointer;
  height: 4px;
}

.hero-slider-value {
  font-family: var(--font-mono);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-left: 6px;
}

/* Warning-Badge */
.hero-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid #f97316;
  border-radius: var(--r-4, 8px);
  background: #fff7ed;
  color: #c2410c;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
}

.hero-warning__icon {
  flex-shrink: 0;
  font-size: 13px;
}

.hero-required {
  color: var(--status-red, #c0392b);
  margin-left: 2px;
}
.hero-textarea {
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 9px 12px;
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
  resize: vertical;
  min-height: 72px;
  line-height: 1.5;
}
.hero-textarea:hover { border-color: var(--hairline-strong); }
.hero-textarea:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
</style>
