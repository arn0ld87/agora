<script setup>
import { ref, computed, onMounted, watch, watchEffect } from 'vue'
import { usePersonaActions } from '../composables/usePersonaActions'
import { usePersonaFilter } from '../composables/usePersonaFilter'
import { usePersonaLibrary } from '../composables/usePersonaLibrary'
import { useSimulationPrepare } from '../composables/useSimulationPrepare'
import { usePersonaQuota } from '../composables/usePersonaQuota'
import { useI18n } from 'vue-i18n'
import { useEnvForm } from '../composables/useEnvForm'
import { useRuntimeLlmOptions, mapRuntimeProviderToBackendId } from '../composables/useRuntimeLlmOptions'
import Button from '@/components/v4/forms/Button.vue'
import Badge from './ui/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import Field from './ui/Field.vue'
import Select from './ui/Select.vue'
import QuotaPlanEditor from './step2/QuotaPlanEditor.vue'
import AddPersonaModal from './step2/AddPersonaModal.vue'
import PersonaDetailModal from './step2/PersonaDetailModal.vue'
import PersonaCardGrid from './step2/PersonaCardGrid.vue'
import PersonaLibraryPanel from './step2/PersonaLibraryPanel.vue'
import {
  buildQuotaPlanFromEntries,
} from '../contracts/personaQuotaContract'
import { checkLlmProviderHasKey } from '../api/llmProviderKeys'
import LlmProfilePicker from '@/components/llm/LlmProfilePicker.vue'

const { t } = useI18n()

const props = defineProps({
  simulationId: String,
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

const useCustomRounds = ref(false)
const customMaxRounds = ref(40)
const useCustomDays = ref(false)
const customSimulationDays = ref(3)
const selectedProfile = ref(null)
const llmProfileId = ref(props.projectData?.llm_profile_id ?? null)
const userPickedProfile = ref(false)
const showRuntimeOptions = ref(false)

// Nach async-Hydration von projectData den Default einmal nachziehen, aber
// niemals, sobald der User selbst eine Wahl getroffen hat (auch nicht für
// "Server-Standard" = null).
watch(
  () => props.projectData?.llm_profile_id,
  (next) => {
    if (userPickedProfile.value) return
    if (next) llmProfileId.value = next
  },
)

watch(llmProfileId, () => {
  userPickedProfile.value = true
})

const {
  runtimeProvider,
  runtimeApiKey,
  runtimeBaseUrl,
  runtimeProviderOptions,
  runtimeProviderEnabled,
  runtimePayload,
  runtimeApiKeyMissing,
} = useRuntimeLlmOptions(t)

// --- DB-Key-Status für Override-Provider (Smoke-Fix Slice 04 + Followup) ---
/** True wenn für den gewählten Override-Provider ein Key in der Settings-DB hinterlegt ist. */
const providerDbHasKey = ref(false)
/** True während der has-key-Status abgefragt wird. */
const providerDbKeyChecking = ref(false)
/** True wenn User trotz DB-Key explizit einen Session-Key eintragen will. */
const showSessionKeyOverride = ref(false)
/** Race-Guard: nur die Antwort für den zuletzt angefragten Provider zählt. */
let _checkProviderDbKeySeq = 0

async function _checkProviderDbKey(providerId) {
  if (!providerId || providerId === 'default') {
    providerDbHasKey.value = false
    return
  }
  // Custom-OpenAI im UI → openai_compatible im Backend-Registry
  // (Copilot PR #466, Step2EnvSetup.vue:67).
  const backendProviderId = mapRuntimeProviderToBackendId(providerId)
  const mySeq = ++_checkProviderDbKeySeq
  providerDbKeyChecking.value = true
  try {
    const result = await checkLlmProviderHasKey(backendProviderId)
    // Stale-Antwort verwerfen: User hat zwischenzeitlich Provider gewechselt
    // (Copilot PR #466, Step2EnvSetup.vue:75).
    if (mySeq !== _checkProviderDbKeySeq) return
    providerDbHasKey.value = result
  } finally {
    if (mySeq === _checkProviderDbKeySeq) {
      providerDbKeyChecking.value = false
    }
  }
}

watchEffect(() => {
  if (runtimeProviderEnabled.value) {
    _checkProviderDbKey(runtimeProvider.value)
  } else {
    providerDbHasKey.value = false
  }
  // Provider-Wechsel oder Toggle-aus: Session-Override-UI zurücksetzen.
  showSessionKeyOverride.value = false
})

// ----- Model + language picker (useEnvForm — Sub-Slice 37, Refs #203) -----

const {
  ollamaModels,
  presetModels,
  defaultModel,
  defaultProvider,
  serverDefaultRequiresOllama,
  ollamaReachable,
  agentToolsEnabled,
  maxToolCallsPerAction,
  loadingModels,
  modelOption,
  customModel,
  language,
  modelOptions,
  loadModels,
  effectiveModel,
} = useEnvForm({ t, onError: (msg) => addLog(msg), runtimeProvider })

// ----- Prepare flow (useSimulationPrepare — Sub-Slice 34, Refs #203) -----

const {
  phase,
  isPreparing,
  prepareProgress,
  progressMessage,
  profiles,
  expectedTotal,
  simulationConfig,
  fetchProfilesRealtime,
  startPrepare,
  probeAlreadyPrepared,
} = useSimulationPrepare()

// Persona review (Slice 2.4): quality badges, approve/reject, inline edit.
// Extracted to usePersonaActions (Sub-Slice 38, Refs #203).
const {
  editingProfile,
  reviewActionPending,
  reviewActionError,
  regenerateHint,
  statusVariant,
  statusLabel,
  issueBadgeVariant,
  startEditingSelected,
  cancelEditing,
  applyProfileToList,
  approveSelected,
  rejectSelected,
  regenerateSelected,
  saveEditingProfile,
  hasRegeneratingPersona,
  personaReview,
} = usePersonaActions({
  simulationId: computed(() => props.simulationId),
  profiles,
  selectedProfile,
  addLog,
})

// Agent-count cap (optional; null = unlimited / all matching entities).
const STORAGE_MAX_AGENTS = 'agora.maxAgents'
const useAgentCap = ref(false)
const maxAgents = ref(Number(localStorage.getItem(STORAGE_MAX_AGENTS)) || 50)
watch(maxAgents, (v) => { localStorage.setItem(STORAGE_MAX_AGENTS, String(v)) })

// ----- Persona-Quota-Plan (Sub-Slice 35: extrahiert nach usePersonaQuota) -----
const {
  useQuotaPlan,
  quotaEntries,
  quotaValidationError,
  quotaTotal,
} = usePersonaQuota({ t })

// Warn wenn Pool kleiner als Quota-Summe (smoke #6)
const belowQuotaWarning = computed(() => {
  if (!useAgentCap.value || !useQuotaPlan.value) return false
  return quotaTotal.value > 0 && maxAgents.value < quotaTotal.value
})

// ----- Persona-Library + CRUD (usePersonaLibrary — Sub-Slice 39, Refs #203) -----
const {
  personaTemplates, isLoadingPersonaLibrary, personaLibraryError,
  savingPersonaKeys, usingPersonaTemplateIds,
  showAddPersonaModal, newPersona, isSavingPersona,
  profileKey, profilePayload,
  resetNewPersona, submitNewPersona,
  loadPersonaLibrary, savePersona, saveAllPersonas,
  usePersonaTemplate, removePersonaTemplate, removePersona,
} = usePersonaLibrary({
  simulationId: computed(() => props.simulationId),
  profiles,
  fetchProfilesRealtime,
  addLog,
})

// ----- Persona-Filter (usePersonaFilter — Sub-Slice 40, Refs #203) -----
const {
  personaSearch,
  showAllPersonas,
  filteredPersonas,
  visiblePersonas,
} = usePersonaFilter({ profiles })

const autoGeneratedRounds = computed(() => {
  if (!simulationConfig.value?.time_config) return null
  const totalHours = simulationConfig.value.time_config.total_simulation_hours
  const minutesPerRound = simulationConfig.value.time_config.minutes_per_round
  if (!totalHours || !minutesPerRound) return null
  return Math.max(Math.floor((totalHours * 60) / minutesPerRound), 40)
})

const autoGeneratedDays = computed(() => {
  if (!simulationConfig.value?.time_config?.total_simulation_hours) return null
  return Math.max(1, Math.round(simulationConfig.value.time_config.total_simulation_hours / 24))
})

function addLog(msg) { emit('add-log', msg) }

// Guard stores the simId for which refreshQuality was last fired.
// Fired once per sim, triggered by Sim-Wechsel OR first profile arrival.
// Guard prevents re-trigger when profile count changes within the same sim.
const _qualityFetchedForSim = ref(null)

watch(
  () => [props.simulationId, profiles.value.length],
  ([simId, n]) => {
    if (!simId) return                                   // no active sim
    if (n <= 0) return                                   // no profiles yet
    if (_qualityFetchedForSim.value === simId) return    // already fired for this sim
    _qualityFetchedForSim.value = simId                  // set guard before call (race-safe)
    // Fire-and-forget; failures surface via personaReview.error.
    personaReview.refreshQuality(simId)
  },
  { immediate: false },
)

async function triggerPrepare() {
  if (!props.simulationId) {
    addLog(t('errors.unknown') + ': simulationId fehlt')
    emit('update-status', 'error')
    return
  }
  // Quota-Validierung via usePersonaQuota (Sub-Slice 35).
  const payload = {
    simulation_id: props.simulationId,
    use_llm_for_profiles: true,
    parallel_profile_count: 5,
    language: language.value,
  }
  if (llmProfileId.value) payload.llm_profile_id = llmProfileId.value
  const m = effectiveModel()
  if (m) payload.llm_model = m
  // Smoke-Fix Slice 04: kein hartes Abbrechen bei fehlendem Session-Key mehr.
  // Backend löst den Key via SecretResolver aus der Settings-DB auf.
  // Wenn weder Session-Key noch DB-Key vorhanden: Backend antwortet 422 mit Fehlermeldung.
  const provider = runtimePayload()
  if (provider) payload.llm_provider = provider
  if (useAgentCap.value && maxAgents.value > 0) {
    // Backend floor steht auf MIN_SIMULATION_AGENTS=10 (Followup zu Slice 05);
    // wir clampen hier nur auf die gleiche Untergrenze, damit Mini-Pool-Smokes
    // (Smoke #6 2026-05-15) tatsächlich mit < 50 Agenten laufen. Persona-Table-
    // Floor (50) skaliert der Report-Pfad via Round-Robin nach (Copilot PR #466).
    payload.max_agents = Math.max(10, maxAgents.value)
  }
  if (useQuotaPlan.value) {
    if (quotaValidationError.value) {
      addLog(`${t('errors.personaGenFailed')}: ${quotaValidationError.value}`)
      emit('update-status', 'error')
      return
    }
    payload.quota_plan = buildQuotaPlanFromEntries(quotaEntries.value)
  }
  await startPrepare({
    payload,
    onLog: addLog,
    onStatusChange: (s) => emit('update-status', s),
  })
}

function handleStart() {
  const params = {}
  if (useCustomRounds.value) params.maxRounds = customMaxRounds.value
  if (useCustomDays.value) params.simulationDays = customSimulationDays.value
  params.simulationId = props.simulationId
  emit('next-step', params)
}

onMounted(() => {
  loadModels()
  loadPersonaLibrary()
  if (props.simulationId) {
    // Probe: if already prepared, hydrate via composable.
    probeAlreadyPrepared(props.simulationId, {
      onLog: addLog,
      onStatusChange: (s) => emit('update-status', s),
    })
  }
})
</script>

<template>
  <div class="step-panel">
    <div class="scroll">

      <!-- Card 0: Setup -->
      <article class="card" :class="{ 'is-active': phase < 1 }">
        <header class="card-head">
          <Kicker num="01">{{ t('step2.title') }}</Kicker>
          <Badge variant="ghost">{{ t('step2.kicker') }}</Badge>
        </header>
        <p class="card-desc">{{ t('step2.sub') }}</p>
        <p v-if="agentToolsEnabled" class="hint warning">
          {{ t('step2.agentTools.warning', { count: maxToolCallsPerAction }) }}
        </p>

        <div class="setup-grid">
          <!-- LLM-Profil (optional, schlägt Model/Provider-Overrides) -->
          <div class="setup-cell setup-cell--wide">
            <LlmProfilePicker v-model="llmProfileId">
              <template #hint>
                <span class="hint">{{ t('step2.llmProfile.hint') }}</span>
              </template>
            </LlmProfilePicker>
          </div>

          <!-- Model -->
          <div class="setup-cell" :class="{ 'is-overridden-by-profile': llmProfileId }">
            <Select
              v-model="modelOption"
              :label="t('step2.model.label')"
              :options="modelOptions"
            />
            <p class="hint" v-if="llmProfileId">{{ t('step2.llmProfile.modelIgnored') }}</p>
            <p class="hint" v-else-if="loadingModels">{{ t('step2.model.loadingModels') }}</p>
            <p class="hint" v-else-if="!runtimeProviderEnabled && serverDefaultRequiresOllama && !ollamaReachable">{{ t('step2.model.noOllama') }}</p>
            <p class="hint" v-else-if="!runtimeProviderEnabled && defaultProvider === 'openai'">{{ t('step2.model.openAiDefault') }}</p>
          </div>

          <!-- Custom model input (when 'custom' chosen) -->
          <div class="setup-cell" v-if="modelOption === 'custom'">
            <Field
              v-model="customModel"
              :label="t('step2.model.customLabel')"
              :placeholder="t('step2.model.customPlaceholder')"
            />
          </div>

          <div class="setup-cell setup-cell--wide">
            <button
              type="button"
              class="runtime-toggle"
              :aria-expanded="showRuntimeOptions"
              @click="showRuntimeOptions = !showRuntimeOptions"
            >
              <span>{{ t('step2.runtimeProvider.toggle') }}</span>
              <span class="meta">
                {{ runtimeProviderEnabled ? t('step2.runtimeProvider.active') : t('step2.runtimeProvider.default') }}
              </span>
            </button>
            <div v-if="showRuntimeOptions" class="runtime-panel">
              <Select
                v-model="runtimeProvider"
                :label="t('step2.runtimeProvider.label')"
                :options="runtimeProviderOptions"
              />
              <template v-if="runtimeProviderEnabled">
                <!-- Statushinweis während DB-Key-Prüfung -->
                <p v-if="providerDbKeyChecking" class="hint">
                  {{ t('step2.runtimeProvider.checkingKey') }}
                </p>
                <!-- DB-Key vorhanden: Banner + Toggle für optionalen Session-Override -->
                <template v-else-if="providerDbHasKey">
                  <p class="hint info provider-override-banner" role="status">
                    {{ t('step2.runtimeProvider.dbKeyPresentBanner', { provider: runtimeProvider }) }}
                  </p>
                  <label class="session-key-toggle">
                    <input
                      type="checkbox"
                      v-model="showSessionKeyOverride"
                    />
                    {{ t('step2.runtimeProvider.sessionKeyOverrideToggle') }}
                  </label>
                </template>
                <!-- Kein DB-Key: Warn-Banner (Pflicht-Eingabe) -->
                <p
                  v-else-if="runtimeApiKeyMissing"
                  class="hint warning provider-override-banner"
                  role="alert"
                >
                  {{ t('step2.runtimeProvider.noDbKeyBanner', { provider: runtimeProvider }) }}
                </p>
                <!-- Key-Feld: nur sichtbar wenn kein DB-Key ODER User explizit überschreibt -->
                <Field
                  v-if="!providerDbHasKey || showSessionKeyOverride"
                  v-model="runtimeApiKey"
                  type="password"
                  :label="t('step2.runtimeProvider.sessionKeyLabel')"
                  :placeholder="t('step2.runtimeProvider.apiKeyPlaceholder')"
                />
                <Field
                  v-model="runtimeBaseUrl"
                  :label="t('step2.runtimeProvider.baseUrl')"
                  :placeholder="t('step2.runtimeProvider.baseUrlPlaceholder')"
                />
              </template>
            </div>
          </div>

          <!-- Agent language -->
          <div class="setup-cell">
            <Select
              v-model="language"
              :label="t('step2.language.label')"
              :options="[
                { value: 'de', label: t('step2.language.de') },
                { value: 'en', label: t('step2.language.en') },
              ]"
            />
            <p class="hint">{{ t('step2.language.hint') }}</p>
          </div>

          <!-- Agent cap (optional) -->
          <div class="setup-cell setup-cell--wide">
            <label class="agent-cap">
              <input type="checkbox" v-model="useAgentCap" :disabled="isPreparing" />
              <span>{{ t('step2.agentCap.label') }}</span>
            </label>
            <div v-if="useAgentCap" class="agent-cap-slider">
              <input
                type="range"
                v-model.number="maxAgents"
                min="10"
                max="500"
                step="5"
                :disabled="isPreparing"
                :title="t('step2.agentCap.minimumHint')"
              />
              <input
                type="number"
                v-model.number="maxAgents"
                min="10"
                max="2000"
                :disabled="isPreparing"
                class="agent-cap-number"
                :title="t('step2.agentCap.minimumHint')"
              />
              <span class="meta">{{ t('step2.agentCap.unit') }}</span>
            </div>
            <p v-if="belowQuotaWarning" class="hint hint--warn" role="alert">
              {{ t('step2.personaPool.belowQuotaWarning', { pool: maxAgents, quota: quotaTotal }) }}
            </p>
            <p class="hint" v-if="!useAgentCap">{{ t('step2.agentCap.unlimitedHint') }}</p>
          </div>

          <!-- Persona-Quota-Plan (Sub-Slice 20c, 24 / 31): UI in QuotaPlanEditor -->
          <div class="setup-cell setup-cell--wide">
            <QuotaPlanEditor
              v-model:enabled="useQuotaPlan"
              v-model:entries="quotaEntries"
              :disabled="isPreparing"
            />
          </div>
        </div>

        <div class="actions">
          <Button variant="ghost" @click="$emit('go-back')">← {{ t('common.back') }}</Button>
          <Button
            variant="primary"
            arrow
            :disabled="isPreparing"
            :loading="isPreparing && phase < 3"
            @click="triggerPrepare"
          >
            {{ phase === 0 ? t('step2.personas.generate') : t('common.processing') }}
          </Button>
        </div>
      </article>

      <!-- Card 1: Personas -->
      <article class="card" :class="{ 'is-active': phase === 1 }" v-if="phase >= 1">
        <header class="card-head">
          <Kicker num="02">{{ t('step2.personas.title') }}</Kicker>
          <Badge :variant="phase > 1 ? 'solid' : 'accent'" :dot="phase === 1">
            <template v-if="phase > 1">{{ t('common.completed') }}</template>
            <template v-else>{{ profiles.length }} / {{ expectedTotal || '?' }}</template>
          </Badge>
        </header>
        <p class="card-desc" v-if="phase === 1">
          {{ t('step2.personas.running', { done: profiles.length, total: expectedTotal || '?' }) }}
        </p>

        <div v-if="profiles.length" class="persona-search">
          <input
            v-model="personaSearch"
            type="search"
            class="persona-search-input"
            :placeholder="t('history.search')"
          />
          <span class="meta">
            {{ filteredPersonas.length }} / {{ profiles.length }}
          </span>
        </div>

        <PersonaCardGrid
          :personas="visiblePersonas"
          :saving-persona-keys="savingPersonaKeys"
          :status-variant="statusVariant"
          :status-label="statusLabel"
          :issue-badge-variant="issueBadgeVariant"
          :get-issues-for="personaReview.getIssuesFor"
          :highest-severity-for="personaReview.highestSeverityFor"
          :profile-key="profileKey"
          @select="selectedProfile = $event"
          @remove="removePersona"
          @save="savePersona"
        />

        <div v-if="phase >= 2" class="persona-actions">
          <Button variant="ghost" @click="showAddPersonaModal = true">+ {{ t('step2.addPersona.title') }}</Button>
          <Button variant="ghost" :disabled="!profiles.length" @click="saveAllPersonas">
            {{ t('step2.personas.saveAll') }}
          </Button>
        </div>
        <PersonaLibraryPanel
          v-if="phase >= 2"
          :templates="personaTemplates"
          :loading="isLoadingPersonaLibrary"
          :error="personaLibraryError"
          :using-ids="usingPersonaTemplateIds"
          @refresh="loadPersonaLibrary"
          @use="usePersonaTemplate"
          @remove="removePersonaTemplate"
        />
        <button
          v-if="filteredPersonas.length > 24 && !showAllPersonas && !personaSearch.trim()"
          class="persona-more-btn"
          @click="showAllPersonas = true"
        >
          + {{ filteredPersonas.length - 24 }} {{ t('common.more') }}
        </button>
        <p v-else-if="!filteredPersonas.length && profiles.length" class="meta">
          {{ t('history.empty') }}
        </p>
      </article>

      <!-- Card 2: Config + start -->
      <article class="card" :class="{ 'is-active': phase >= 2 }" v-if="phase >= 2">
        <header class="card-head">
          <Kicker num="03" accent>{{ t('step3.config.title') }}</Kicker>
          <Badge :variant="phase >= 3 ? 'accent' : 'outline'" :dot="phase === 2">
            {{ phase >= 3 ? t('common.ready') : t('common.processing') }}
          </Badge>
        </header>

        <div class="rounds">
          <label class="rounds-radio">
            <input type="radio" :value="false" v-model="useCustomDays" />
            <span>
              {{ t('step3.config.days') }}: {{ autoGeneratedDays || '?' }}
              <small class="meta">{{ t('step3.config.automatic') }}</small>
            </span>
          </label>
          <label class="rounds-radio">
            <input type="radio" :value="true" v-model="useCustomDays" />
            <span>
              {{ t('step3.config.days') }}:
              <input
                v-model.number="customSimulationDays"
                type="number"
                min="1"
                max="365"
                class="rounds-input"
              />
              <small class="meta">{{ t('step3.config.customValue') }}</small>
            </span>
          </label>
          <label class="rounds-radio">
            <input type="radio" :value="false" v-model="useCustomRounds" />
            <span>
              {{ t('step3.config.rounds') }}: {{ autoGeneratedRounds || '?' }}
              <small class="meta">{{ t('step3.config.automatic') }}</small>
            </span>
          </label>
          <label class="rounds-radio">
            <input type="radio" :value="true" v-model="useCustomRounds" />
            <span>
              {{ t('step3.config.rounds') }}:
              <input
                v-model.number="customMaxRounds"
                type="number"
                min="1"
                max="500"
                class="rounds-input"
              />
              <small class="meta">{{ t('step3.config.customValue') }}</small>
            </span>
          </label>
        </div>

        <div class="actions">
          <Button
            variant="primary"
            arrow
            :disabled="phase < 3 || hasRegeneratingPersona"
            :title="hasRegeneratingPersona ? t('step2.persona.regeneratingBlock') : undefined"
            @click="handleStart"
          >
            {{ t('step3.controls.start') }}
          </Button>
        </div>
        <p v-if="hasRegeneratingPersona" class="hint hint--warn">
          {{ t('step2.persona.regeneratingBlock') }}
        </p>
      </article>
    </div>
    <PersonaDetailModal
      :selected-profile="selectedProfile"
      :editing-profile="editingProfile"
      :review-action-pending="reviewActionPending"
      :review-action-error="reviewActionError"
      :regenerate-hint="regenerateHint"
      :review-enabled="personaReview.reviewEnabled.value"
      :status-variant="statusVariant"
      :status-label="statusLabel"
      :issue-badge-variant="issueBadgeVariant"
      :get-issues-for="personaReview.getIssuesFor"
      :highest-severity-for="personaReview.highestSeverityFor"
      @update:selected-profile="selectedProfile = $event"
      @update:editing-profile="editingProfile = $event"
      @update:regenerate-hint="regenerateHint = $event"
      @start-editing="startEditingSelected"
      @cancel-editing="cancelEditing"
      @approve="approveSelected"
      @reject="rejectSelected"
      @regenerate="regenerateSelected"
      @save="saveEditingProfile"
    />
    <AddPersonaModal
      :open="showAddPersonaModal"
      :persona="newPersona"
      :saving="isSavingPersona"
      @update:open="showAddPersonaModal = $event"
      @update:persona="newPersona = $event"
      @submit="submitNewPersona"
    />
  </div>
</template>

<style scoped>
.step-panel {
  height: 100%;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--s-6);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}

.card {
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card.is-active { border-color: var(--accent); }
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.card-desc { color: var(--fg-body); margin: 0; }

.setup-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--s-5) var(--s-7);
}
.setup-cell { display: flex; flex-direction: column; gap: var(--s-2); }
.setup-cell--wide { grid-column: 1 / -1; }
.setup-cell.is-overridden-by-profile { opacity: 0.6; }

.runtime-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--s-3);
  width: 100%;
  min-height: var(--ctl-h-md);
  padding: 0 var(--ctl-pad-x);
  border: 1px solid var(--rule-strong);
  border-radius: var(--r-1);
  background: var(--bg-elevated);
  color: var(--fg);
  cursor: pointer;
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.runtime-toggle:hover { border-color: color-mix(in oklch, var(--fg) 30%, transparent); }
.runtime-panel {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s-4);
  padding: var(--s-4);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  background: var(--bg-subtle);
}

.agent-cap {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 12px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg);
  cursor: pointer;
}
.agent-cap-slider {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  margin-top: var(--s-2);
}
.agent-cap-slider input[type=range] {
  flex: 1;
  accent-color: var(--accent);
}
.agent-cap-number {
  width: 80px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-16);
  padding: 4px 0;
  color: var(--fg);
  outline: none;
  text-align: right;
}
.agent-cap-number:focus { border-bottom-color: var(--accent); }
.hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin: 0;
}

.actions {
  display: flex;
  gap: var(--s-3);
  justify-content: flex-end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-4);
}

.persona-actions {
  display: flex;
  gap: var(--s-3);
  justify-content: flex-end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}

.rounds {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.rounds-radio {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  cursor: pointer;
}
.rounds-input {
  width: 80px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-16);
  padding: 4px 0;
  margin: 0 var(--s-2);
  color: var(--fg);
  outline: none;
}
.rounds-input:focus { border-bottom-color: var(--accent); }

.persona-search {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.persona-search-input {
  flex: 1;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  padding: var(--s-2) 0;
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  color: var(--fg);
  outline: none;
}
.persona-search-input:focus { border-bottom-color: var(--accent); }

.persona-more-btn {
  background: transparent;
  border: 1px dashed var(--rule-strong);
  border-radius: var(--r-1);
  padding: var(--s-3);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
}
.persona-more-btn:hover { color: var(--accent); border-color: var(--accent); }

@media (max-width: 720px) {
  .setup-grid { grid-template-columns: 1fr; }
  .runtime-panel { grid-template-columns: 1fr; }
}

.hint--warn {
  color: var(--warn, #c89020);
}

/* Design v3 shell pass: Apple grouped controls and sans-only typography. */
.step-panel {
  background: var(--surface-canvas, var(--bg));
  color: var(--text-primary, var(--fg));
  font-family: var(--font-sans, var(--ff-sans));
}
.scroll {
  padding: var(--sp-6, var(--s-6));
  gap: var(--sp-5, var(--s-5));
}
.card {
  background: var(--surface-elevated, var(--bg));
  border-color: var(--hairline, var(--rule));
  border-radius: var(--r-7, var(--r-1));
  box-shadow: var(--shadow-1);
}
.card.is-active {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-tint-bg, var(--accent-soft)), var(--shadow-1);
}
.card-head,
.persona-actions,
.rounds,
.persona-search {
  border-color: var(--separator, var(--rule));
}
.card-desc,
.hint,
.meta {
  color: var(--text-secondary, var(--fg-muted));
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
}
.setup-cell,
.runtime-panel,
.rounds-radio {
  background: var(--surface-inset, var(--bg-elevated));
  border-radius: var(--r-6, var(--r-1));
}
.runtime-panel {
  border: 1px solid var(--hairline, var(--rule));
  padding: var(--sp-4, var(--s-4));
}
.rounds-input,
.persona-search-input,
.agent-cap-number {
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-1));
  color: var(--text-primary, var(--fg));
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  padding: 7px 10px;
}
.rounds-input:focus,
.persona-search-input:focus,
.agent-cap-number:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}
.persona-more-btn {
  border-style: solid;
  border-color: var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-1));
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
  background: var(--surface-elevated, transparent);
}
</style>
