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
import AiModelPicker from '../forms/AiModelPicker.vue'
import Button from '../forms/Button.vue'
import IconPlus from '../shell/icons/IconPlus.vue'
import RunBudgetForm from '../run-budget/RunBudgetForm.vue'
import PreflightEstimateCard from '../run-budget/PreflightEstimateCard.vue'
import { fetchLlmProfiles } from '../../../api/llmProfiles'
import { preflightEstimate } from '../../../api/budget'
import type { PreflightEstimateParams } from '../../../api/budget'
import { setPendingUpload } from '../../../store/pendingUpload'
import { STORAGE_LANG } from '../../../composables/useEnvForm'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import { setRunModelOverride, clearRunModelOverride } from '@/store/runModelOverride'
import type { LlmProfile } from '../../../contracts/llmProfileContract'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type {
  PreflightEstimate,
  RunBudgetConfig,
} from '../../../contracts/runBudgetContract'
import { getSystemStatus } from '../../../api/status'
import { getAvailableModels } from '../../../api/simulation'

const { t } = useI18n()
const router = useRouter()

const ALLOWED = ['.pdf', '.md', '.txt', '.markdown']

const files = ref<File[]>([])
const isDragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const errorMsg = ref('')

const llmProfiles = ref<LlmProfile[]>([])

// ---- Service-Readiness (Parität zu Home.vue, Portierung aus #915) ----
// Liefert die Werte, die Home.vue aus /api/simulation/available-models zieht,
// damit der Dashboard-Start denselben Service-Readiness-Gate besitzt wie der
// klassische /home-Flow: Neo4j muss erreichbar sein; Ollama nur, wenn es der
// Default-Provider ist — außer der User hat explizit ein anderes Modell
// gewählt (hasExplicitPick), dann übernimmt der gewählte Provider.
const defaultProvider = ref<string>('unknown')
const ollamaReachable = ref<boolean>(false)
const neo4jReachable = ref<boolean>(false)

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
 * Slice A2 (2026-05-17) + Slice 5.4 (2026-07-13): Modell-Auswahl auf den
 * projektweiten AiModelPicker konsolidiert. Hybrid-Mode:
 *   - Profile-Dropdown (links): LLM-Profile aus fetchLlmProfiles. Wenn gewählt,
 *     gewinnt das Profile — Provider/Modell/Temperatur kommen aus dem Profile.
 *   - AiModelPicker (rechts, sichtbar wenn kein Profile aktiv): Direkt-Auswahl
 *     aus den unter /settings/llm-providers hinterlegten Provider-Connections.
 *
 * Persistenz: `agora.hero.profileId` (Preset). Phase-1 Konsolidierung: Das
 * Default-Modell kommt NICHT mehr aus einem eigenen `agora.hero.aiModelRef`-Key,
 * sondern aus dem Kanon (routing/defaults.global via useEffectiveModelSelection)
 * — damit der Dashboard-Start dieselbe Auswahl wie Settings zeigt. Ein
 * Dashboard-Pick ist ein transienter Run-Override als voller AiModelRef in der sessionStorage-Senke
 * `agora.run.aiModelRefOverride` (store/runModelOverride), die Step3Simulation
 * beim Sim-Start vorrangig vor dem Kanon als `ai_model_ref` sendet.
 * Slice 7.6c (Storage-Cut): Der Legacy-Key `agora.hero.route` wird
 * NICHT mehr gelesen und beim Mount defensiv entfernt.
 */
const STORAGE_HERO_PROFILE_ID = 'agora.hero.profileId'
// Slice 7.6c (Storage-Cut): nur noch als Ziel für defensives removeLocal.
const STORAGE_HERO_ROUTE_LEGACY = 'agora.hero.route'

// Phase-1 Konsolidierung: Default-Modell kommt aus dem Kanon
// (routing/defaults.global via useEffectiveModelSelection), nicht mehr aus
// einem eigenen localStorage-Key.
const effectiveModel = useEffectiveModelSelection()

const selectedProfileId = ref<string | null>(readLocal(STORAGE_HERO_PROFILE_ID))
const selectedModel = ref<AiModelRef | null>(null)
// Run-Override nur bei explizitem Picker-Pick schreiben: selectedModel wird
// beim Mount aus dem Kanon initialisiert und darf den Kanon nicht als
// Override festschreiben — spätere Kanon-Änderungen sollen bis zum Sim-Start
// durchschlagen (Review-Finding PR #853).
const hasExplicitPick = ref(false)
const language = ref<string>(readLocal(STORAGE_LANG) || 'de')
const simulationRequirement = ref('')

// Persona-Floor synchron mit Backend (simulation_config_generator._validate_persona_quota).
// Hard-Floor=30, optional override via AGORA_ALLOW_SMALL_SIM=1. Wert wird beim
// Mount per /api/status (backend.allow_small_sim) gezogen — bis dahin pessimistisch
// auf den harten Floor klemmen, damit der User keine Run-Konfig zusammenklicken kann
// die das Backend dann mit 422 ablehnt.
const NUM_AGENTS_HARD_FLOOR = 30
const NUM_AGENTS_OVERRIDE_FLOOR = 10
const NUM_AGENTS_DEFAULT = NUM_AGENTS_HARD_FLOOR
const NUM_AGENTS_MAX = 100
const NUM_ROUNDS_MIN = 3
const NUM_ROUNDS_DEFAULT = 10
const NUM_ROUNDS_MAX = 30

const allowSmallSim = ref<boolean>(false)
const numAgents = ref<number>(NUM_AGENTS_DEFAULT)
const numRounds = ref<number>(NUM_ROUNDS_DEFAULT)

// ---- Issue #764: optionale Run-Budgets + Preflight-Schätzung ----
// Das Budget wandert über den pendingUpload-Store zu Step3Simulation, die es
// beim Sim-Start als `budget` an /api/simulation/start durchreicht. Die
// Preflight-Schätzung ist rein informativ (is_estimate=true) und wird per
// Button aktualisiert — bewusst kein Debounce auf jeden Slider-Tick.
const budget = ref<RunBudgetConfig | null>(null)
const estimate = ref<PreflightEstimate | null>(null)
const estimateLoading = ref<boolean>(false)
const estimateError = ref<string | null>(null)

async function refreshEstimate() {
  estimateLoading.value = true
  estimateError.value = null
  try {
    const params: PreflightEstimateParams = {
      num_agents: numAgents.value,
      max_rounds: numRounds.value,
    }
    // Expliziter Picker-Pick gewinnt; sonst der Kanon (routing/defaults.global).
    const modelRef = hasExplicitPick.value
      ? selectedModel.value
      : effectiveModel.effectiveRef.value
    if (modelRef?.provider_connection_id && modelRef?.model_id) {
      params.ai_model_ref = {
        provider_connection_id: modelRef.provider_connection_id,
        model_id: modelRef.model_id,
      }
    }
    const res = await preflightEstimate(params)
    if (res?.success && res.data) {
      estimate.value = res.data
    } else {
      estimateError.value = res?.error || 'unknown'
    }
  } catch (e) {
    estimateError.value = e instanceof Error ? e.message : String(e)
  } finally {
    estimateLoading.value = false
  }
}

const numAgentsMin = computed<number>(
  () => (allowSmallSim.value ? NUM_AGENTS_OVERRIDE_FLOOR : NUM_AGENTS_HARD_FLOOR),
)

const showAgentsWarning = computed<boolean>(
  () => allowSmallSim.value && numAgents.value >= NUM_AGENTS_OVERRIDE_FLOOR && numAgents.value < NUM_AGENTS_HARD_FLOOR,
)

const profileOptions = computed(() => {
  return llmProfiles.value.map(p => ({
    value: p.id,
    label: `${p.name} — ${p.model_name}${p.is_default ? ` (${t('dashboard.hero.profileDefault')})` : ''}`,
  }))
})

const serverDefaultRequiresOllama = computed(() => defaultProvider.value === 'ollama')

// Service-Readiness-Gate (Parität zu Home.vue, #915): blockt den Start, wenn
// Neo4j nicht erreichbar ist oder der Default-Provider Ollama ist und Ollama
// nicht erreichbar ist — außer der User hat explizit ein anderes Modell
// gewählt (hasExplicitPick), dann übernimmt der gewählte Provider.
const servicesReady = computed(
  () =>
    neo4jReachable.value &&
    (!serverDefaultRequiresOllama.value || ollamaReachable.value || hasExplicitPick.value),
)

const canSubmit = computed(
  () =>
    files.value.length > 0 &&
    simulationRequirement.value.trim() !== '' &&
    servicesReady.value,
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
  // Append-Verhalten (Parität zu Home.vue, #915): neue gültige Files werden an
  // bestehende angehängt, nicht ersetzt — mehrfaches Drop/Picker-Interaktion
  // sammelt statt zu überschreiben.
  files.value = [...files.value, ...accepted]
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

function onPickModel(aiRef: AiModelRef | null) {
  // Der volle Ref wird erst beim Start gespeichert; eine leere Auswahl räumt
  // einen möglicherweise älteren tab-skopierten Override sofort auf.
  hasExplicitPick.value = true
  selectedModel.value = aiRef
  if (aiRef) {
    removeLocal(STORAGE_HERO_ROUTE_LEGACY)
  } else {
    removeLocal(STORAGE_HERO_ROUTE_LEGACY)
    clearRunModelOverride()
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
    // Wenn ein Profile aktiv ist, gewinnt es — direct-AiModelRef ignorieren.
    if (profileId) {
      // Profile gewinnt — Run-Override defensiv räumen, damit Step3 nicht
      // einen stale Direkt-Pick vorzieht.
      clearRunModelOverride()
    } else {
      // Voller AiModelRef (inkl. provider_connection_id) als transienter
      // Run-Override: Step3Simulation sendet ihn beim Sim-Start vorrangig
      // vor dem Kanon als autoritatives ai_model_ref. Nur bei explizitem
      // Picker-Pick — der Kanon-Initialwert vom Mount wird nicht eingefroren.
      if (hasExplicitPick.value && selectedModel.value) {
        setRunModelOverride(selectedModel.value)
      } else {
        clearRunModelOverride()
      }
    }
    setPendingUpload(
      files.value,
      simulationRequirement.value.trim(),
      profileId,
      numAgents.value,
      numRounds.value,
      budget.value,
    )
    router.push({ name: 'Process', params: { projectId: 'new' } })
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(() => {
  // Slice 7.6c (Storage-Cut): Legacy-Route-Key einmalig defensiv entsorgen.
  removeLocal(STORAGE_HERO_ROUTE_LEGACY)
  // Phase-1 Konsolidierung: Default-Modell aus dem Kanon initialisieren, damit
  // der Dashboard-Start dieselbe Auswahl wie Settings zeigt.
  effectiveModel
    .ensureLoaded()
    .then(() => {
      if (!selectedModel.value) selectedModel.value = effectiveModel.effectiveRef.value
    })
    .catch(() => { /* Kanon nicht ladbar: Picker bleibt leer, Backend nutzt active-config */ })
  fetchLlmProfiles()
    .then(profiles => {
      llmProfiles.value = profiles
      // Stale-Persistenz-Gate: `agora.hero.profileId` überlebt das Löschen des
      // Profils im Backend. Eine tote ID würde als `profile_id` an den Sim-Start
      // gehen und dort mit "LLM-Profil ... nicht gefunden" abbrechen — die
      // Auswahl deshalb verwerfen, sobald sie nicht mehr in der Liste steht.
      if (selectedProfileId.value && !profiles.some(p => p.id === selectedProfileId.value)) {
        selectedProfileId.value = null
        removeLocal(STORAGE_HERO_PROFILE_ID)
      }
    })
    .catch(() => { /* Fallback: Profile-Picker bleibt leer, ModelPicker greift */ })
  // backend.allow_small_sim aus /api/status spiegelt AGORA_ALLOW_SMALL_SIM
  // wider. Default-pessimistisch bei Fetch-Fehler: harter 30er-Floor bleibt.
  getSystemStatus()
    .then(envelope => {
      const backend = (envelope?.data?.backend ?? envelope?.backend) as { allow_small_sim?: boolean } | undefined
      allowSmallSim.value = !!backend?.allow_small_sim
      // Wenn der Override nach Mount inaktiv ist, klemmen wir einen ggf. aus
      // dem letzten Override-Run persistenten Slider-Wert wieder hoch.
      if (!allowSmallSim.value && numAgents.value < NUM_AGENTS_HARD_FLOOR) {
        numAgents.value = NUM_AGENTS_HARD_FLOOR
      }
    })
    .catch(() => { /* Fail-safe: allowSmallSim bleibt false → 30er-Floor aktiv */ })
  // Service-Readiness + Backend-Default-Language (Parität zu Home.vue, #915).
  // Liefert default_provider/ollama_reachable/neo4j_reachable/default_language
  // aus /api/simulation/available-models. Bei Fetch-Fehler bleiben die Refs
  // pessimistisch auf false → servicesReady blockt den Start (wie Home.vue).
  getAvailableModels()
    .then(res => {
      const data = (res?.data ?? {}) as {
        default_provider?: string
        ollama_reachable?: boolean
        neo4j_reachable?: boolean
        default_language?: string
      }
      if (!res?.success) return
      defaultProvider.value = data.default_provider || 'unknown'
      ollamaReachable.value = !!data.ollama_reachable
      neo4jReachable.value = !!data.neo4j_reachable
      if (data.default_language && !readLocal(STORAGE_LANG)) {
        language.value = data.default_language
      }
    })
    .catch(() => { /* Fail-safe: servicesReady bleibt false → Submit blockt */ })
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
          <AiModelPicker
            :model-value="selectedModel"
            :placeholder="$t('dashboard.hero.modelPlaceholder')"
            mode="chat"
            @update:model-value="onPickModel"
          />
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-lang">{{ $t('dashboard.hero.languageLabel') }}</label>
          <select id="hero-lang" v-model="language" class="hero-select">
            <option value="de">{{ $t('dashboard.hero.languageDe') }}</option>
            <option value="en">{{ $t('dashboard.hero.languageEn') }}</option>
          </select>
        </div>
        <div class="hero-field">
          <label class="hero-label" for="hero-num-agents">
            {{ $t('dashboard.hero.numAgentsLabel') }}
            <span class="hero-slider-value">{{ numAgents }}</span>
            <span v-if="allowSmallSim" class="hero-small-sim-badge" :title="$t('dashboard.hero.smallSimActiveTooltip')">
              {{ $t('dashboard.hero.smallSimBadge') }}
            </span>
          </label>
          <input
            id="hero-num-agents"
            v-model.number="numAgents"
            type="range"
            :min="numAgentsMin"
            :max="NUM_AGENTS_MAX"
            step="1"
            class="hero-slider"
            :aria-valuenow="numAgents"
            :aria-valuemin="numAgentsMin"
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
          <details class="hero-budget">
            <summary class="hero-label hero-budget__summary">
              {{ $t('runBudget.sectionTitle') }}
            </summary>
            <div class="hero-budget__body">
              <RunBudgetForm v-model="budget" />
              <PreflightEstimateCard
                :estimate="estimate"
                :loading="estimateLoading"
                :error="estimateError"
              />
              <div class="hero-budget__estimate-actions">
                <Button
                  variant="ghost"
                  size="sm"
                  :loading="estimateLoading"
                  @click="refreshEstimate"
                >
                  {{ $t('runBudget.estimateRefresh') }}
                </Button>
              </div>
            </div>
          </details>
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

/* Budget-Section (Issue #764): aufklappbarer Block in Zone 2 */
.hero-budget {
  border: 1px solid var(--hairline);
  border-radius: var(--r-4, 8px);
  background: var(--surface-inset, #f2f2f7);
  padding: 10px 12px;
}

.hero-budget__summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.hero-budget__summary::before {
  content: '▸';
  font-size: 10px;
  transition: transform 120ms ease;
}

.hero-budget[open] .hero-budget__summary::before {
  transform: rotate(90deg);
}

.hero-budget__summary:focus-visible {
  outline: none;
  border-radius: var(--r-3, 6px);
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.hero-budget__body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
}

.hero-budget__estimate-actions {
  display: flex;
  justify-content: flex-end;
}

@media (prefers-reduced-motion: reduce) {
  .hero-budget__summary::before {
    transition: none;
  }
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

.hero-small-sim-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 6px;
  border: 1px solid #f97316;
  border-radius: 999px;
  background: #fff7ed;
  color: #c2410c;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  cursor: help;
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
