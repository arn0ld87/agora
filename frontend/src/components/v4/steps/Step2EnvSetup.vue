<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { usePersonaActions } from '../../../composables/usePersonaActions'
import { usePersonaFilter } from '../../../composables/usePersonaFilter'
import { usePersonaLibrary } from '../../../composables/usePersonaLibrary'
import { useSimulationPrepare } from '../../../composables/useSimulationPrepare'
import { usePersonaQuota } from '../../../composables/usePersonaQuota'
import { useI18n } from 'vue-i18n'
import { useEnvForm } from '../../../composables/useEnvForm'
import Button from '@/components/v4/forms/Button.vue'
import Badge from '@/components/v4/forms/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import DegradationNotice from '@/components/v4/DegradationNotice.vue'
import QuotaPlanEditor from '../../step2/QuotaPlanEditor.vue'
import AddPersonaModal from '../../step2/AddPersonaModal.vue'
import PersonaDetailModal from '../../step2/PersonaDetailModal.vue'
import PersonaCardGrid from '../../step2/PersonaCardGrid.vue'
import PersonaLibraryPanel from '../../step2/PersonaLibraryPanel.vue'
import { useOperatorAccess } from '../../../composables/useOperatorAccess'
import EnvSetupModelPanel from '../../step2/EnvSetupModelPanel.vue'
import SimulationStartConfig from '../../step2/SimulationStartConfig.vue'
import AgentCapControl from '../../step2/AgentCapControl.vue'
import ContestedQuestionField from '../../step2/ContestedQuestionField.vue'
import ActivityModeField from '../../step2/ActivityModeField.vue'
import { ActivityModeSchema } from '../../../contracts/simulationActivityContract'
import {
  buildQuotaPlanFromEntries,
} from '../../../contracts/personaQuotaContract'
import { ContestedQuestionSchema } from '../../../contracts/contestedQuestionContract'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'

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

const selectedModelRef = ref(null)
// Expliziter Nutzer-Pick — strikt getrennt vom Anzeige-Default. Der beim Mount
// aus dem Kanon (routing/defaults.global_default) übernommene Wert befüllt nur
// selectedModelRef (Anzeige) und darf keinen Request-Override erzeugen —
// sonst würde ein bloß akzeptierter Workspace-Default das konfigurierte
// Projekt-Profil unterdrücken und den prepared-Shortcut umgehen.
const selectedModelOverride = ref(null)

function onModelRefPicked(val) {
  selectedModelRef.value = val
  selectedModelOverride.value = val
}

// ----- Model + language picker (useEnvForm) -----
const {
  defaultProvider,
  serverDefaultRequiresOllama,
  ollamaReachable,
  agentToolsEnabled,
  maxToolCallsPerAction,
  loadingModels,
  language,
  loadModels,
} = useEnvForm({ t, onError: (msg) => addLog(msg) })

// ----- Prepare flow (useSimulationPrepare) -----
const {
  phase,
  isPreparing,
  profiles,
  expectedTotal,
  personaFloorApplied,
  personaFloor,
  simulationConfig,
  degradations,
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

// ----- Streitfrage (#1778) -----
// Eingabe vor der Vorbereitung; leer heißt, der Assistent schlägt eine vor.
const contestedQuestionInput = ref('')

// Geltende Streitfrage aus der erzeugten Konfiguration. Vertragswidrige oder
// fehlende Daten (Altbestand) zeigen nichts an, statt einen Fehler zu werfen.
const appliedContestedQuestion = computed(() => {
  const parsed = ContestedQuestionSchema.safeParse(simulationConfig.value?.contested_question)
  if (!parsed.success) return null
  const { origin, statement, absence_reason: reason } = parsed.data
  if (origin === 'none') {
    return {
      text: reason
        ? t('step2.contestedQuestion.none', { reason })
        : t('step2.contestedQuestion.noneWithoutReason'),
      origin: '',
    }
  }
  return {
    text: t('step2.contestedQuestion.applied', { statement }),
    origin: t(
      origin === 'user'
        ? 'step2.contestedQuestion.originUser'
        : 'step2.contestedQuestion.originAssistant',
    ),
  }
})

// ----- Aktivitätsmodus (#1779) -----
// Gesendet wird der Modus nur nach einer ausdrücklichen Wahl. Ohne sie
// entscheidet der Server (Einstellung AGORA_SIM_ACTIVITY_MODE, Standard
// realistic), und eine bereits vorbereitete Simulation wird nicht allein
// wegen der Vorauswahl erneut vorbereitet: ein ausdrücklich übergebener,
// abweichender Modus hebt den Kurzschluss `already_prepared` auf.
const activityMode = ref('realistic')
const activityModeChosen = ref(false)

function chooseActivityMode(mode) {
  activityMode.value = mode
  activityModeChosen.value = true
}

// Wirksamer Modus aus der erzeugten Konfiguration. Ältere Simulationen tragen
// kein `time_config.activity_model` und zeigen den Hinweis auf das bisherige Modell.
watch(
  () => simulationConfig.value?.time_config?.activity_model?.mode,
  (mode) => {
    const parsed = ActivityModeSchema.safeParse(mode)
    if (parsed.success && !activityModeChosen.value) activityMode.value = parsed.data
  },
  { immediate: true },
)

const appliedActivityMode = computed(() => {
  const timeConfig = simulationConfig.value?.time_config
  if (!timeConfig) return null
  const parsed = ActivityModeSchema.safeParse(timeConfig.activity_model?.mode)
  if (!parsed.success) return t('step2.activityMode.legacy')
  return t('step2.activityMode.applied', {
    mode: t(`step2.activityMode.${parsed.data}.label`),
  })
})

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
const operatorAccess = useOperatorAccess()

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

// ----- UAT-004: widerspruchsfreier Abschluss-Status -----
// Wirksamer Floor für die Statusbewertung: Backend-Vertragswert
// (persona_target.floor, Report-Gate-Zahl), sonst als letzte Auskunft der
// eigentliche Ziel-Nenner; fehlt beides, ist nichts bestätigt → nie
// "Abgeschlossen" behaupten (T-261010-01).
const completedBelowFloor = computed(() => {
  const effectiveFloor = personaFloor.value ?? (expectedTotal.value ?? Infinity)
  return profiles.value.length >= effectiveFloor
})
const completedBadgeTone = computed(() => (completedBelowFloor.value ? 'green' : 'orange'))
const completedBadgeLabel = computed(() =>
  completedBelowFloor.value ? t('common.completed') : t('common.incomplete'),
)

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
    ...(activityModeChosen.value ? { activity_mode: activityMode.value } : {}),
  }
  if (selectedModelOverride.value !== null) {
    payload.ai_model_ref = { ...selectedModelOverride.value, source: 'explicit' }
  } else {
    if (props.projectData?.llm_profile_id) {
      payload.llm_profile_id = props.projectData.llm_profile_id
    }
  }
  if (useAgentCap.value && maxAgents.value > 0) {
    payload.max_agents = Math.max(10, maxAgents.value)
  }
  const contestedQuestion = contestedQuestionInput.value.trim()
  if (contestedQuestion) {
    payload.contested_question = contestedQuestion
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

onMounted(async () => {
  loadModels()
  // Persona-Bibliothek ist Betreiber-Zustand (operator_only, #1617).
  if (operatorAccess.value) loadPersonaLibrary()
  try {
    const effectiveModelSel = useEffectiveModelSelection()
    await effectiveModelSel.ensureLoaded()
    if (!selectedModelRef.value) {
      selectedModelRef.value = effectiveModelSel.effectiveRef.value
    }
  } catch {
    // Kanon nicht ladbar
  }
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
          <Badge tone="gray" :dot="false">{{ t('step2.kicker') }}</Badge>
        </header>
        <p class="card-desc">{{ t('step2.sub') }}</p>

        <EnvSetupModelPanel
          v-model:language="language"
          :model-ref="selectedModelRef"
          @update:model-ref="onModelRefPicked"
          :agent-tools-enabled="agentToolsEnabled"
          :max-tool-calls-per-action="maxToolCallsPerAction"
        />

        <!-- Streitfrage (#1778): Eingabe vor, Anzeige nach der Vorbereitung -->
        <ContestedQuestionField
          v-model="contestedQuestionInput"
          :is-preparing="isPreparing"
        />
        <p
          v-if="appliedContestedQuestion"
          class="contested-question-applied"
          data-testid="contested-question-applied"
        >
          {{ appliedContestedQuestion.text }}
          <span v-if="appliedContestedQuestion.origin" class="meta">{{ appliedContestedQuestion.origin }}</span>
        </p>

        <!-- Aktivitätsmodus (#1779) -->
        <ActivityModeField
          :model-value="activityMode"
          :is-preparing="isPreparing"
          @update:model-value="chooseActivityMode"
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
            {{ phase === 0 && !isPreparing ? t('step2.personas.generate') : (isPreparing ? t('common.processing') : t('step2.personas.regenerate')) }}
          </Button>
        </div>
      </article>

      <!-- Card 1: Personas -->
      <article class="card" :class="{ 'is-active': phase === 1 }" v-if="phase >= 1">
        <header class="card-head">
          <Kicker num="02">{{ t('step2.personas.title') }}</Kicker>
          <Badge
            :tone="phase === 1 ? 'blue' : (completedBelowFloor ? 'green' : 'orange')"
            :dot="phase === 1"
            data-testid="personas-status-badge"
          >
            {{ profiles.length }} / {{ expectedTotal || '?' }}
            <template v-if="phase > 1"> {{ completedBadgeLabel }}</template>
          </Badge>
        </header>
        <p class="card-desc" v-if="phase === 1">
          {{ t('step2.personas.running', { done: profiles.length, total: expectedTotal || '?' }) }}
        </p>
        <!-- Issue #1034: Ohne diesen Hinweis wirkt der Nenner willkürlich —
             sieben Entitäten ergeben fünfzig Personas, weil der Report-Contract
             eine Mindestzahl verlangt. -->
        <p class="card-hint" v-if="phase >= 1 && personaFloorApplied">
          {{ t('step2.personas.floorApplied', { total: expectedTotal || '?' }) }}
        </p>
        <!-- UAT-004: Mindestanzahl aus dem Backend-Vertrag — dieselbe Zahl,
             an der das Report-Gate misst (report_agent/workflow.py), statt
             einer clientseitig abgeleiteten. -->
        <p
          class="card-hint"
          v-if="phase >= 1 && personaFloor !== null"
          data-testid="personas-floor-hint"
        >
          {{ t('step2.agentCap.reportFloor', { floor: personaFloor }) }}
        </p>

        <!-- Issue #1759: stille Teilausfälle des Prepare-Jobs sichtbar machen. -->
        <DegradationNotice :report="degradations" />

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
          :can-save="operatorAccess"
          @remove="removePersona"
          @save="savePersona"
        />

        <div v-if="phase >= 2" class="persona-actions">
          <Button variant="ghost" @click="showAddPersonaModal = true">+ {{ t('step2.addPersona.title') }}</Button>
          <Button v-if="operatorAccess" variant="ghost" :disabled="!profiles.length" @click="saveAllPersonas">
            {{ t('step2.personas.saveAll') }}
          </Button>
        </div>
        <PersonaLibraryPanel
          v-if="phase >= 2 && operatorAccess"
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
        :applied-activity-mode="appliedActivityMode"
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
  background: var(--surface-canvas);
  color: var(--text-primary);
  font-family: var(--font-sans);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}
.card {
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-7);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
  box-shadow: var(--shadow-1);
}
.card.is-active {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-tint-bg), var(--shadow-1);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--separator);
  padding-bottom: var(--s-3);
}
.card-desc { color: var(--fg-body); margin: 0; }
.contested-question-applied { color: var(--fg-body); margin: 0; }
.hint {
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--text-secondary);
  margin: 0;
}
.hint--warn { color: var(--warn); }
.meta { color: var(--text-secondary); font-family: var(--font-sans); }
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
  border-top: 1px solid var(--separator);
  padding-top: var(--s-3);
}
.persona-search {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  border-top: 1px solid var(--separator);
  padding-top: var(--s-3);
}
.persona-search-input {
  flex: 1;
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  padding: 7px 10px;
  font-family: var(--font-sans);
  font-size: var(--fs-16);
  color: var(--text-primary);
  outline: none;
}
.persona-search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--focus-ring);
}
.persona-more-btn {
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  padding: var(--s-3);
  font-family: var(--font-sans);
  font-size: 11px;
  color: var(--fg-muted);
  cursor: pointer;
  transition: border-color 150ms ease, color 150ms ease;
}
.persona-more-btn:hover { color: var(--accent); border-color: var(--accent); }
</style>