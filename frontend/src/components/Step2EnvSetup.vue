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
import QuotaPlanEditor from './step2/QuotaPlanEditor.vue'
import AddPersonaModal from './step2/AddPersonaModal.vue'
import PersonaDetailModal from './step2/PersonaDetailModal.vue'
import PersonaCardGrid from './step2/PersonaCardGrid.vue'
import PersonaLibraryPanel from './step2/PersonaLibraryPanel.vue'
import EnvSetupModelPanel from './step2/EnvSetupModelPanel.vue'
import SimulationStartConfig from './step2/SimulationStartConfig.vue'
import AgentCapControl from './step2/AgentCapControl.vue'
import {
  buildQuotaPlanFromEntries,
} from '../contracts/personaQuotaContract'
import { checkLlmProviderHasKey } from '../api/llmProviderKeys'

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
const showSessionKeyOverride = ref(false)

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
/** Race-Guard: nur die Antwort für den zuletzt angefragten Provider zählt. */
let _checkProviderDbKeySeq = 0

async function _checkProviderDbKey(providerId) {
  if (!providerId || providerId === 'default') {
    providerDbHasKey.value = false
    return
  }
  const backendProviderId = mapRuntimeProviderToBackendId(providerId)
  const mySeq = ++_checkProviderDbKeySeq
  providerDbKeyChecking.value = true
  try {
    const result = await checkLlmProviderHasKey(backendProviderId)
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
  showSessionKeyOverride.value = false
})

// ----- Model + language picker (useEnvForm) -----
const {
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

// ----- Prepare flow (useSimulationPrepare) -----
const {
  phase,
  isPreparing,
  profiles,
  expectedTotal,
  simulationConfig,
  fetchProfilesRealtime,
  startPrepare,
  probeAlreadyPrepared,
} = useSimulationPrepare()

// Persona review actions
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

// Agent-count cap
const STORAGE_MAX_AGENTS = 'agora.maxAgents'
const useAgentCap = ref(false)
const maxAgents = ref(Number(localStorage.getItem(STORAGE_MAX_AGENTS)) || 50)
watch(maxAgents, (v) => { localStorage.setItem(STORAGE_MAX_AGENTS, String(v)) })

// ----- Persona-Quota-Plan -----
const {
  useQuotaPlan,
  quotaEntries,
  quotaValidationError,
  quotaTotal,
} = usePersonaQuota({ t })

const belowQuotaWarning = computed(() => {
  if (!useAgentCap.value || !useQuotaPlan.value) return false
  return quotaTotal.value > 0 && maxAgents.value < quotaTotal.value
})

// ----- Persona-Library + CRUD -----
const {
  personaTemplates, isLoadingPersonaLibrary, personaLibraryError,
  savingPersonaKeys, usingPersonaTemplateIds,
  showAddPersonaModal, newPersona, isSavingPersona,
  profileKey,
  submitNewPersona,
  loadPersonaLibrary, savePersona, saveAllPersonas,
  usePersonaTemplate, removePersonaTemplate, removePersona,
} = usePersonaLibrary({
  simulationId: computed(() => props.simulationId),
  profiles,
  fetchProfilesRealtime,
  addLog,
})

// ----- Persona-Filter -----
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

const _qualityFetchedForSim = ref(null)

watch(
  () => [props.simulationId, profiles.value.length],
  ([simId, n]) => {
    if (!simId) return
    if (n <= 0) return
    if (_qualityFetchedForSim.value === simId) return
    _qualityFetchedForSim.value = simId
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
  const payload = {
    simulation_id: props.simulationId,
    use_llm_for_profiles: true,
    language: language.value,
  }
  if (llmProfileId.value) payload.llm_profile_id = llmProfileId.value
  const m = effectiveModel()
  if (m) payload.llm_model = m
  const provider = runtimePayload()
  if (provider) payload.llm_provider = provider
  if (useAgentCap.value && maxAgents.value > 0) {
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

        <EnvSetupModelPanel
          v-model:model-option="modelOption"
          v-model:custom-model="customModel"
          v-model:language="language"
          v-model:llm-profile-id="llmProfileId"
          v-model:runtime-provider="runtimeProvider"
          v-model:runtime-api-key="runtimeApiKey"
          v-model:runtime-base-url="runtimeBaseUrl"
          v-model:show-session-key-override="showSessionKeyOverride"
          :model-options="modelOptions"
          :loading-models="loadingModels"
          :runtime-provider-enabled="runtimeProviderEnabled"
          :server-default-requires-ollama="serverDefaultRequiresOllama"
          :ollama-reachable="ollamaReachable"
          :default-provider="defaultProvider"
          :agent-tools-enabled="agentToolsEnabled"
          :max-tool-calls-per-action="maxToolCallsPerAction"
          :runtime-provider-options="runtimeProviderOptions"
          :runtime-api-key-missing="runtimeApiKeyMissing"
          :provider-db-has-key="providerDbHasKey"
          :provider-db-key-checking="providerDbKeyChecking"
          :is-preparing="isPreparing"
        />

        <!-- Agent cap (optional) -->
        <AgentCapControl
          v-model:use-agent-cap="useAgentCap"
          v-model:max-agents="maxAgents"
          :is-preparing="isPreparing"
          :below-quota-warning="belowQuotaWarning"
          :quota-total="quotaTotal"
        />

        <!-- Persona-Quota-Plan -->
        <QuotaPlanEditor
          v-model:enabled="useQuotaPlan"
          v-model:entries="quotaEntries"
          :disabled="isPreparing"
        />

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

      <!-- Card 2: Config + start (extracted to SimulationStartConfig) -->
      <SimulationStartConfig
        :phase="phase"
        v-model:use-custom-rounds="useCustomRounds"
        v-model:custom-max-rounds="customMaxRounds"
        v-model:use-custom-days="useCustomDays"
        v-model:custom-simulation-days="customSimulationDays"
        :auto-generated-rounds="autoGeneratedRounds"
        :auto-generated-days="autoGeneratedDays"
        :has-regenerating-persona="hasRegeneratingPersona"
        @start="handleStart"
      />
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
  background: var(--surface-canvas, var(--bg));
  color: var(--text-primary, var(--fg));
  font-family: var(--font-sans, var(--ff-sans));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-6, var(--s-6));
  display: flex;
  flex-direction: column;
  gap: var(--sp-5, var(--s-5));
}
.card {
  background: var(--surface-elevated, var(--bg));
  border: 1px solid var(--hairline, var(--rule));
  border-radius: var(--r-7, var(--r-1));
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  box-shadow: var(--shadow-1);
}
.card.is-active {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-tint-bg, var(--accent-soft)), var(--shadow-1);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--separator, var(--rule));
  padding-bottom: var(--s-3);
}
.card-desc { color: var(--fg-body); margin: 0; }
.hint {
  font-family: var(--font-sans, var(--ff-sans));
  font-size: 11px;
  color: var(--text-secondary, var(--fg-muted));
  margin: 0;
}
.hint--warn { color: var(--warn, #c89020); }
.meta { color: var(--text-secondary, var(--fg-muted)); font-family: var(--font-sans, var(--ff-sans)); }
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
  border-top: 1px solid var(--separator, var(--rule));
  padding-top: var(--s-3);
}
.persona-search {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  border-top: 1px solid var(--separator, var(--rule));
  padding-top: var(--s-3);
}
.persona-search-input {
  flex: 1;
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-1));
  padding: 7px 10px;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: var(--fs-16);
  color: var(--text-primary, var(--fg));
  outline: none;
}
.persona-search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring, var(--accent-soft));
}
.persona-more-btn {
  background: var(--surface-elevated, transparent);
  border: 1px solid var(--hairline, var(--rule-strong));
  border-radius: var(--r-5, var(--r-1));
  padding: var(--s-3);
  font-family: var(--font-sans, var(--ff-sans));
  font-size: 11px;
  color: var(--fg-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
}
.persona-more-btn:hover { color: var(--accent); border-color: var(--accent); }
</style>
