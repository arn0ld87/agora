<script setup lang="ts">
/**
 * NewRunDialog — Startdialog „Neuer Lauf“ (#1799, Etappe 3, Bauplan §3.4).
 *
 * Ein Dialog, fünf Gruppen, kein Assistent: Frage, Graph, Personasatz, Modelle,
 * Umfang und Budget. Er liegt als Fenster über der zuletzt gezeigten Ansicht
 * (gleicher Mechanismus wie das Einstellungsfenster, siehe App.vue und
 * `isWindowRoute`).
 *
 * Was das Backend heute kann, steht hier ehrlich: Die Frage gehört zum Graphen,
 * „Ohne Graph“ und gespeicherte Personasätze gibt es noch nicht, ein Modell
 * oder Profil gilt für den Aufruf, dem es mitgegeben wird.
 */
import { computed, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'
import AiModelPicker from '@/components/v4/forms/AiModelPicker.vue'
import Button from '@/components/v4/forms/Button.vue'
import RunBudgetForm from '@/components/v4/run-budget/RunBudgetForm.vue'
import PreflightEstimateCard from '@/components/v4/run-budget/PreflightEstimateCard.vue'
import AgentCapControl from '@/components/step2/AgentCapControl.vue'
import ContestedQuestionField from '@/components/step2/ContestedQuestionField.vue'
import ActivityModeField from '@/components/step2/ActivityModeField.vue'
import SourceDropzone from './SourceDropzone.vue'
import { fetchLlmProfiles } from '@/api/llmProfiles'
import { preflightEstimate } from '@/api/budget'
import type { PreflightEstimateParams } from '@/api/budget'
import { getAvailableModels } from '@/api/simulation'
import { setPendingUpload } from '@/store/pendingUpload'
import { clearRunModelOverride, setRunModelOverride } from '@/store/runModelOverride'
import { toRunParamsQuery, MAX_SIMULATION_DAYS } from '@/contracts/runParamsQuery'
import type { DocumentRole } from '@/contracts/documentRoleContract'
import type { LlmProfile } from '@/contracts/llmProfileContract'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type { ActivityMode } from '@/contracts/simulationActivityContract'
import type { PreflightEstimate, RunBudgetConfig } from '@/contracts/runBudgetContract'
import { STORAGE_LANG } from '@/composables/useEnvForm'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import { useOperatorAccess } from '@/composables/useOperatorAccess'
import { SETTINGS_FALLBACK_PATH } from '@/components/settings-window/sections'
import { useSettingsWindowStore } from '@/stores/settingsWindow'
import { useNewRunGraphs } from '@/composables/new-run/useNewRunGraphs'
import { useNewRunBudgetDefaults } from '@/composables/new-run/useNewRunBudgetDefaults'
import { useNewRunSubmit } from '@/composables/new-run/useNewRunSubmit'
import { usePersonaSets } from '@/composables/personaSets/usePersonaSets'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const windowStore = useSettingsWindowStore()
const operatorAccess = useOperatorAccess()
const effectiveModel = useEffectiveModelSelection()

const uid = useId()
const id = (name: string): string => `${uid}-${name}`

/** Auslöser merken, bevor reka-ui den Fokus ins Fenster zieht. */
const opener: Element | null = typeof document === 'undefined' ? null : document.activeElement

// ---- Grenzen (wie im Bestand von HeroNewRun / Schritt 2) ----
const MIN_AGENTS = 10
const DEFAULT_AGENTS = 30
const MIN_ROUNDS = 3
const MAX_ROUNDS = 30
const DEFAULT_ROUNDS = 24
const DEFAULT_DAYS = 1
const CONTESTED_MIN = 10
const CONTESTED_MAX = 300
const STORAGE_PROFILE_ID = 'agora.hero.profileId'

// ---- Speicher-Helfer ----
function readLocal(key: string): string | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage?.getItem(key) ?? null
  } catch {
    return null
  }
}
function writeLocal(key: string, value: string | null): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    /* Speicher gesperrt: die Auswahl gilt nur für diesen Dialog. */
  }
}

// ---- Gruppe 1: Frage ----
const question = ref('')
const contestedQuestion = ref('')

// ---- Gruppe 2: Graph ----
type GraphMode = 'existing' | 'new'
const graphMode = ref<GraphMode>('new')
const selectedProjectId = ref('')
const files = ref<File[]>([])
const documentRoles = ref<DocumentRole[]>([])
const fileError = ref('')
const graphsSource = useNewRunGraphs()
const { graphs } = graphsSource

// ---- Gruppe 3: Personasatz (#1807) ----
// Der Lauf aus einem Satz geht ohne Graph. Ein eigener Modus, weil
// „kein Graph waehlen" im Graph-Weg eine Abweichung waere und hier der
// einzige Weg ist.
type PersonaMode = 'generate' | 'set'
const personaMode = ref<PersonaMode>('generate')
const personaSets = usePersonaSets()
const { sets: personaSetOptions } = personaSets
const selectedPersonaSetId = ref('')

const selectedPersonaSet = computed(() =>
  personaSetOptions.value.find((s) => s.id === selectedPersonaSetId.value) ?? null,
)
// Ein gesperrter Satz taugt als Quelle: daraus darf immer wieder ein Lauf
// entstehen — gesperrt ist nur das Bearbeiten der Personas.
const personaSetUsable = computed(() => personaSetOptions.value.filter((s) => s.entry_count > 0))

const selectedGraph = computed(() => graphs.value.find((g) => g.projectId === selectedProjectId.value) ?? null)
const existingGraphs = computed(() => graphsSource.graphs.value.length > 0)

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('de-DE')
}
function graphLabel(g: { name: string; updatedAt: string; question: string | null }): string {
  const q = g.question ? ` — ${g.question.length > 70 ? `${g.question.slice(0, 70)}…` : g.question}` : ''
  return `${g.name} (${formatDate(g.updatedAt)})${q}`
}

// ---- Gruppe 3: Personasatz ----
const useAgentCap = ref(true)
const maxAgents = ref(DEFAULT_AGENTS)

// ---- Gruppe 4: Modelle ----
const llmProfiles = ref<LlmProfile[]>([])
const profilesSettled = ref(false)
const neo4jReachable = ref(false)
const selectedProfileId = ref<string | null>(readLocal(STORAGE_PROFILE_ID))
const selectedModel = ref<AiModelRef | null>(null)
const hasExplicitPick = ref(false)
const language = ref<string>(readLocal(STORAGE_LANG) || 'de')

const profileOptions = computed(() =>
  llmProfiles.value.map((p) => ({
    value: p.id,
    label: `${p.name} — ${p.model_name}${p.is_default ? ` (${t('dashboard.hero.profileDefault')})` : ''}`,
  })),
)
// Workspace-Sessions haben keinen lesbaren Kanon-Default (#1688): ausdrückliche Wahl.
const workspaceModelMissing = computed(
  () => !operatorAccess.value && !(hasExplicitPick.value && selectedModel.value),
)

function discardPersistedProfile(): void {
  selectedProfileId.value = null
  writeLocal(STORAGE_PROFILE_ID, null)
}
function onPickProfile(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  selectedProfileId.value = value || null
  writeLocal(STORAGE_PROFILE_ID, value || null)
}
function onPickModel(aiRef: AiModelRef | null): void {
  hasExplicitPick.value = true
  selectedModel.value = aiRef
  if (!aiRef) clearRunModelOverride()
}

// ---- Gruppe 5: Umfang und Budget ----
const days = ref(DEFAULT_DAYS)
const rounds = ref(DEFAULT_ROUNDS)
const activityMode = ref<ActivityMode>('realistic')
const budgetDefaults = useNewRunBudgetDefaults()
const budget = ref<RunBudgetConfig | null>(null)
const budgetTouched = ref(false)
const estimate = ref<PreflightEstimate | null>(null)
const estimateLoading = ref(false)
const estimateError = ref<string | null>(null)

/** Geändert gegenüber der Vorbelegung: nur dann wird ein Budget mitgesendet. */
const budgetChanged = computed(
  () => JSON.stringify(budget.value) !== JSON.stringify(budgetDefaults.defaults.value),
)
function onBudgetUpdate(next: RunBudgetConfig | null): void {
  budgetTouched.value = true
  budget.value = next
}

async function refreshEstimate(): Promise<void> {
  estimateLoading.value = true
  estimateError.value = null
  try {
    const params: PreflightEstimateParams = { num_agents: maxAgents.value, max_rounds: rounds.value }
    const modelRef = hasExplicitPick.value ? selectedModel.value : effectiveModel.effectiveRef.value
    if (modelRef?.provider_connection_id && modelRef?.model_id) {
      params.ai_model_ref = {
        provider_connection_id: modelRef.provider_connection_id,
        model_id: modelRef.model_id,
      }
    }
    const res = await preflightEstimate(params)
    if (res?.success && res.data) estimate.value = res.data
    else estimateError.value = res?.error || t('errors.unknown')
  } catch (e) {
    estimateError.value = e instanceof Error ? e.message : String(e)
  } finally {
    estimateLoading.value = false
  }
}

// ---- Aufrufe ----
const submit = useNewRunSubmit()
const uploadError = ref('')
const busy = computed(() => submit.busy.value)

// ---- Prüfungen ----
const servicesReady = computed(() => neo4jReachable.value)
const contestedLength = computed(() => contestedQuestion.value.trim().length)
const contestedValid = computed(
  () => contestedLength.value === 0 || (contestedLength.value >= CONTESTED_MIN && contestedLength.value <= CONTESTED_MAX),
)
const agentsValid = computed(() => !useAgentCap.value || (Number.isInteger(maxAgents.value) && maxAgents.value >= MIN_AGENTS))
const daysValid = computed(() => Number.isInteger(days.value) && days.value >= 1 && days.value <= MAX_SIMULATION_DAYS)
const roundsValid = computed(() => Number.isInteger(rounds.value) && rounds.value >= MIN_ROUNDS && rounds.value <= MAX_ROUNDS)
// Im Satz-Weg ist die Frage ebenfalls Pflicht: der Lauf bekommt keinen
// Graphen, aber `simulation_requirement` verlangt der Endpunkt trotzdem.
const questionMissing = computed(
  () => (graphMode.value === 'new' || personaMode.value === 'set') && question.value.trim() === '',
)

/** Alle offenen Voraussetzungen als Klartext — nicht nur ein gesperrter Knopf. */
const blockers = computed<string[]>(() => {
  const list: string[] = []
  if (graphMode.value === 'existing' && !selectedGraph.value) list.push(t('views.newRun.blockers.graph'))
  // Der Satz-Weg braucht keine Quelldatei: die Personas kommen aus dem Satz,
  // und der Graph wird gar nicht gebaut. Ohne diese Ausnahme bliebe der
  // Startknopf immer gesperrt, weil `graphMode` auf „new" steht.
  const fromPersonaSet = personaMode.value === 'set'
  if (graphMode.value === 'new' && !fromPersonaSet) {
    if (files.value.length === 0) list.push(t('views.newRun.blockers.files'))
    if (questionMissing.value) list.push(t('views.newRun.blockers.question'))
  }
  if (fromPersonaSet) {
    if (questionMissing.value) list.push(t('views.newRun.blockers.question'))
    if (!selectedPersonaSet.value) list.push(t('views.newRun.blockers.personaSet'))
  }
  if (!contestedValid.value) list.push(t('views.newRun.blockers.contested'))
  if (!agentsValid.value) list.push(t('views.newRun.blockers.agents'))
  if (!daysValid.value) list.push(t('views.newRun.blockers.days'))
  if (!roundsValid.value) list.push(t('views.newRun.blockers.rounds'))
  if (!servicesReady.value) list.push(t('dashboard.hero.servicesUnavailableHint'))
  if (!profilesSettled.value) list.push(t('dashboard.hero.profilesLoadingHint'))
  if (workspaceModelMissing.value) list.push(t('dashboard.hero.workspaceModelRequiredHint'))
  return list
})
const canSubmit = computed(() => blockers.value.length === 0 && !busy.value)

// ---- Aktionen ----
function currentModelRef(): AiModelRef | null {
  return hasExplicitPick.value && selectedModel.value ? selectedModel.value : null
}

function applyModelOverride(): void {
  // Wie im Dashboard-Start: ein Profil gewinnt, ein Direkt-Pick wird zum Run-Override.
  const ref = currentModelRef()
  if (selectedProfileId.value || !ref) clearRunModelOverride()
  else setRunModelOverride(ref)
}

function existingInput() {
  const g = selectedGraph.value
  if (!g) return null
  return {
    projectId: g.projectId,
    graphId: g.graphId,
    language: language.value,
    maxAgents: useAgentCap.value ? maxAgents.value : null,
    contestedQuestion: contestedQuestion.value,
    activityMode: activityMode.value,
    profileId: selectedProfileId.value,
    modelRef: currentModelRef(),
    budget: budgetChanged.value ? budget.value : null,
    maxRounds: rounds.value,
    simulationDays: days.value,
  }
}

async function onCreateOnly(): Promise<void> {
  const input = existingInput()
  if (!canSubmit.value || !input) return
  await submit.createOnly(input)
}

async function onStart(): Promise<void> {
  if (!canSubmit.value) return
  uploadError.value = ''
  writeLocal(STORAGE_LANG, language.value)
  applyModelOverride()
  // Der Satz-Weg geht ohne Graph und ueber einen eigenen Endpunkt. Er kommt
  // vor dem Graph-Zweig: er traegt weder Datei noch Graph und wuerde dort
  // einen Lauf ohne Graph erzeugen, den es nicht gibt.
  if (personaMode.value === 'set' && selectedPersonaSet.value) {
    await submit.createFromPersonaSet({
      personaSetId: selectedPersonaSet.value.id,
      simulationRequirement: question.value.trim(),
      language: language.value,
      maxRounds: rounds.value,
      simulationDays: days.value,
      budget: budgetChanged.value ? budget.value : null,
    })
    return
  }
  if (graphMode.value === 'existing') {
    const input = existingInput()
    if (input) await submit.createAndPrepare(input)
    return
  }
  try {
    setPendingUpload(
      files.value,
      question.value.trim(),
      selectedProfileId.value,
      maxAgents.value,
      rounds.value,
      files.value.map((_f, i) => documentRoles.value[i] ?? 'domain_fact'),
    )
    await router.push({
      name: 'Process',
      params: { projectId: 'new' },
      query: toRunParamsQuery({
        maxRounds: rounds.value,
        simulationDays: days.value,
        budget: budgetChanged.value ? budget.value : null,
      }),
    })
  } catch (e) {
    uploadError.value = e instanceof Error ? e.message : String(e)
  }
}

function close(): void {
  const target = windowStore.returnTo ?? SETTINGS_FALLBACK_PATH
  const back = (window.history.state as { back?: string | null } | null)?.back
  if (back && back === target) router.back()
  else void router.replace(target)
}

function restoreFocus(event: Event): void {
  event.preventDefault()
  if (opener instanceof HTMLElement && opener.isConnected && opener !== document.body) opener.focus()
}

// ---- Laden ----
const queryGraph = computed(() => (typeof route.query.graph === 'string' ? route.query.graph : ''))

watch(
  () => graphsSource.graphs.value,
  (list) => {
    if (selectedProjectId.value && list.some((g) => g.projectId === selectedProjectId.value)) return
    const wanted = list.find((g) => g.projectId === queryGraph.value)
    if (wanted) {
      selectedProjectId.value = wanted.projectId
      graphMode.value = 'existing'
    }
  },
)
watch(graphMode, (mode) => {
  if (mode === 'existing' && !selectedProjectId.value && graphs.value[0]) {
    selectedProjectId.value = graphs.value[0].projectId
  }
})
watch(
  () => budgetDefaults.defaults.value,
  (next) => {
    if (!budgetTouched.value) budget.value = next
  },
)

onMounted(() => {
  void graphsSource.load(t('views.newRun.graph.loadError'))
  // Die Satz-Auswahl braucht ihre Liste, sonst stuende das Feld leer, ohne
  // dass der Nutzt den Unterschied zu „kein Satz vorhanden" erkennt.
  void personaSets.reload()
  void budgetDefaults.load()
  if (!operatorAccess.value) {
    discardPersistedProfile()
    profilesSettled.value = true
  } else {
    effectiveModel
      .ensureLoaded()
      .then(() => {
        if (!selectedModel.value) selectedModel.value = effectiveModel.effectiveRef.value
      })
      .catch(() => { /* Kanon nicht ladbar: der Picker bleibt leer */ })
    fetchLlmProfiles()
      .then((profiles) => {
        llmProfiles.value = profiles
        if (selectedProfileId.value && !profiles.some((p) => p.id === selectedProfileId.value)) {
          discardPersistedProfile()
        }
      })
      .catch(() => discardPersistedProfile())
      .finally(() => { profilesSettled.value = true })
  }
  getAvailableModels()
    .then((res) => {
      if (!res?.success) return
      const data = res.data as { neo4j_reachable?: boolean; default_language?: string }
      neo4jReachable.value = !!data.neo4j_reachable
      if (data.default_language && !readLocal(STORAGE_LANG)) language.value = data.default_language
    })
    .catch(() => { /* neo4jReachable bleibt false: der Hinweis nennt es */ })
})

const questionText = computed(() => {
  if (graphMode.value === 'existing') {
    return selectedGraph.value?.question ?? t('views.newRun.question.noneStored')
  }
  return question.value
})
const phaseText = computed(() =>
  submit.phase.value === 'prepare' ? t('views.newRun.progress.prepare') : t('views.newRun.progress.create'),
)
const startLabel = computed(() =>
  graphMode.value === 'new' ? t('views.newRun.actions.buildGraph') : t('views.newRun.actions.start'),
)
</script>

<template>
  <DialogRoot :open="true" @update:open="(open: boolean) => { if (!open) close() }">
    <DialogPortal>
      <DialogOverlay class="nr-overlay" />
      <DialogContent
        class="nr"
        :aria-describedby="undefined"
        data-testid="new-run-dialog"
        @close-auto-focus="restoreFocus"
      >
        <header class="nr__header">
          <DialogTitle class="nr__title">{{ t('views.newRun.title') }}</DialogTitle>
          <DialogClose class="nr__close" :aria-label="t('views.newRun.close')">
            <span aria-hidden="true">✕</span>
          </DialogClose>
        </header>

        <form class="nr__body" novalidate @submit.prevent="onStart">
          <!-- 1. Frage -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.question.legend') }}</legend>
            <div class="nr__field">
              <label class="nr__label" :for="id('question')">
                {{ t('views.newRun.question.label') }}
                <span v-if="graphMode === 'new' || personaMode === 'set'" class="nr__required" aria-hidden="true">*</span>
              </label>
              <textarea
                :id="id('question')"
                class="nr__textarea"
                rows="3"
                :required="graphMode === 'new' || personaMode === 'set'"
                :readonly="graphMode === 'existing'"
                :value="questionText"
                :placeholder="t('dashboard.hero.requirementPlaceholder')"
                :aria-describedby="graphMode === 'existing' ? id('question-note') : undefined"
                data-testid="new-run-question"
                @input="question = ($event.target as HTMLTextAreaElement).value"
              />
              <p v-if="graphMode === 'existing'" :id="id('question-note')" class="nr__hint">
                {{ t('views.newRun.question.belongsToGraph') }}
              </p>
            </div>
            <ContestedQuestionField v-model="contestedQuestion" :is-preparing="busy || graphMode === 'new'" />
            <p v-if="graphMode === 'new'" class="nr__hint">{{ t('views.newRun.question.contestedLater') }}</p>
          </fieldset>

          <!-- 2. Graph -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.graph.legend') }}</legend>

            <div class="nr__radio">
              <input
                :id="id('graph-existing')"
                v-model="graphMode"
                type="radio"
                name="graph-mode"
                value="existing"
                :disabled="!existingGraphs"
                :aria-describedby="!existingGraphs ? id('graph-existing-why') : undefined"
              />
              <div class="nr__radio-text">
                <label :for="id('graph-existing')">{{ t('views.newRun.graph.existing') }}</label>
                <p v-if="!existingGraphs" :id="id('graph-existing-why')" class="nr__hint">
                  {{ graphsSource.loading.value ? t('views.newRun.graph.loading') : (graphsSource.error.value || t('views.newRun.graph.noneYet')) }}
                </p>
                <template v-else>
                  <label class="nr__sr" :for="id('graph-select')">{{ t('views.newRun.graph.selectLabel') }}</label>
                  <select
                    :id="id('graph-select')"
                    v-model="selectedProjectId"
                    class="nr__select"
                    :disabled="graphMode !== 'existing'"
                    data-testid="new-run-graph-select"
                  >
                    <option v-for="g in graphsSource.graphs.value" :key="g.projectId" :value="g.projectId">
                      {{ graphLabel(g) }}
                    </option>
                  </select>
                </template>
                <p v-if="graphsSource.rejected.value > 0" class="nr__hint" role="status">
                  {{ t('views.newRun.graph.rejected', { n: graphsSource.rejected.value }) }}
                </p>
              </div>
            </div>

            <div class="nr__radio">
              <input
                :id="id('graph-new')"
                v-model="graphMode"
                type="radio"
                name="graph-mode"
                value="new"
              />
              <div class="nr__radio-text">
                <label :for="id('graph-new')">{{ t('views.newRun.graph.fromSource') }}</label>
                <SourceDropzone
                  v-if="graphMode === 'new'"
                  v-model:files="files"
                  v-model:document-roles="documentRoles"
                  :disabled="busy"
                  @rejected="fileError = t('errors.fileTypeNotAllowed')"
                  @accepted="fileError = ''"
                />
                <p v-if="fileError" class="nr__error" role="alert">{{ fileError }}</p>
              </div>
            </div>

            <div class="nr__radio nr__radio--off">
              <input
                :id="id('graph-none')"
                type="radio"
                name="graph-mode"
                value="none"
                disabled
                :aria-describedby="id('graph-none-why')"
              />
              <div class="nr__radio-text">
                <label :for="id('graph-none')">{{ t('views.newRun.graph.none') }}</label>
                <p :id="id('graph-none-why')" class="nr__hint">{{ t('views.newRun.graph.noneWhy') }}</p>
              </div>
            </div>
          </fieldset>

          <!-- 3. Personasatz -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.personas.legend') }}</legend>
            <div class="nr__radio">
              <input :id="id('personas-generate')" type="radio" name="persona-mode" value="generate" checked />
              <div class="nr__radio-text">
                <label :for="id('personas-generate')">{{ t('views.newRun.personas.generate') }}</label>
                <AgentCapControl
                  v-model:use-agent-cap="useAgentCap"
                  v-model:max-agents="maxAgents"
                  :is-preparing="busy"
                />
                <p v-if="graphMode === 'new'" class="nr__hint">{{ t('views.newRun.personas.laterWithSource') }}</p>
              </div>
            </div>
            <!-- Vor Etappe 7 stand hier ein dauerhaft deaktiviertes Feld mit
                 dem Hinweis, der Satz komme spaeter. Jetzt waehlt es einen
                 Satz aus der Bibliothek; der Lauf entsteht ohne Graph
                 (Maintainer-Entscheid 07.10.). -->
            <div class="nr__radio" :class="{ 'nr__radio--off': personaMode !== 'set' }">
              <input
                :id="id('personas-set')"
                v-model="personaMode"
                type="radio"
                name="persona-mode"
                value="set"
                :disabled="busy"
                :aria-describedby="id('personas-set-why')"
              />
              <div class="nr__radio-text">
                <label :for="id('personas-set')">{{ t('views.newRun.personas.set') }}</label>
                <p :id="id('personas-set-why')" class="nr__hint">
                  {{ t('views.newRun.personas.setWhy') }}
                </p>
                <template v-if="personaMode === 'set'">
                  <label class="nr__label" :for="id('persona-set-picker')">
                    {{ t('views.newRun.personas.chooseSet') }}
                  </label>
                  <select
                    :id="id('persona-set-picker')"
                    class="nr__select"
                    v-model="selectedPersonaSetId"
                    :disabled="busy || personaSets.loading.value"
                    data-testid="new-run-persona-set"
                  >
                    <option value="">
                      {{ personaSets.loading.value
                        ? t('views.newRun.personas.loadingSets')
                        : t('views.newRun.personas.noSetChosen') }}
                    </option>
                    <option v-for="opt in personaSetUsable" :key="opt.id" :value="opt.id">
                      {{ opt.name }} ({{ t('views.newRun.personas.count', { n: opt.entry_count }) }})
                    </option>
                  </select>
                  <p v-if="personaSetUsable.length === 0 && !personaSets.loading.value" class="nr__hint">
                    {{ t('views.newRun.personas.noSetsYet') }}
                  </p>
                  <p v-if="selectedPersonaSet" class="nr__hint">
                    {{ t('views.newRun.personas.noGraphNotice') }}
                  </p>
                </template>
              </div>
            </div>
          </fieldset>

          <!-- 4. Modelle -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.models.legend') }}</legend>
            <div v-if="operatorAccess" class="nr__field">
              <label class="nr__label" :for="id('profile')">{{ t('dashboard.hero.profileLabel') }}</label>
              <select
                :id="id('profile')"
                class="nr__select"
                :value="selectedProfileId ?? ''"
                data-testid="new-run-profile"
                @change="onPickProfile"
              >
                <option value="">{{ t('dashboard.hero.profileNone') }}</option>
                <option v-for="opt in profileOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </div>
            <div v-if="!selectedProfileId" class="nr__field">
              <span :id="id('model-label')" class="nr__label">{{ t('dashboard.hero.modelLabel') }}</span>
              <AiModelPicker
                :model-value="selectedModel"
                :placeholder="t('dashboard.hero.modelPlaceholder')"
                mode="chat"
                @update:model-value="onPickModel"
              />
            </div>
            <div class="nr__field">
              <label class="nr__label" :for="id('lang')">{{ t('dashboard.hero.languageLabel') }}</label>
              <select :id="id('lang')" v-model="language" class="nr__select">
                <option value="de">{{ t('dashboard.hero.languageDe') }}</option>
                <option value="en">{{ t('dashboard.hero.languageEn') }}</option>
              </select>
            </div>
            <p class="nr__hint">{{ t('views.newRun.models.scope') }}</p>
          </fieldset>

          <!-- 5. Umfang und Budget -->
          <fieldset class="nr__group" :disabled="busy">
            <legend class="nr__legend">{{ t('views.newRun.scope.legend') }}</legend>
            <div class="nr__row">
              <div class="nr__field">
                <label class="nr__label" :for="id('days')">{{ t('views.newRun.scope.days') }}</label>
                <input
                  :id="id('days')"
                  v-model.number="days"
                  class="nr__number"
                  type="number"
                  min="1"
                  :max="MAX_SIMULATION_DAYS"
                  step="1"
                  :aria-invalid="daysValid ? undefined : 'true'"
                />
              </div>
              <div class="nr__field">
                <label class="nr__label" :for="id('rounds')">{{ t('views.newRun.scope.rounds') }}</label>
                <input
                  :id="id('rounds')"
                  v-model.number="rounds"
                  class="nr__number"
                  type="number"
                  :min="MIN_ROUNDS"
                  :max="MAX_ROUNDS"
                  step="1"
                  :aria-invalid="roundsValid ? undefined : 'true'"
                />
              </div>
            </div>
            <ActivityModeField v-model="activityMode" :is-preparing="busy" />
            <p v-if="graphMode === 'new'" class="nr__hint">{{ t('views.newRun.scope.activityLater') }}</p>

            <div class="nr__field">
              <span class="nr__label">{{ t('runBudget.sectionTitle') }}</span>
              <p v-if="budgetDefaults.state.value === 'unavailable'" class="nr__hint" data-testid="new-run-budget-unavailable">
                {{ t('views.newRun.scope.budgetUnavailable') }}
              </p>
              <RunBudgetForm :model-value="budget" :disabled="busy" @update:model-value="onBudgetUpdate" />
              <p v-if="budgetChanged" class="nr__hint" data-testid="new-run-budget-replaces">
                {{ t('views.newRun.scope.budgetReplaces') }}
              </p>
            </div>

            <PreflightEstimateCard :estimate="estimate" :loading="estimateLoading" :error="estimateError" />
            <div>
              <Button
                variant="ghost"
                size="sm"
                :loading="estimateLoading"
                :disabled="!useAgentCap || !agentsValid"
                @click="refreshEstimate"
              >
                {{ t('runBudget.estimateRefresh') }}
              </Button>
              <p v-if="!useAgentCap" class="nr__hint">{{ t('views.newRun.scope.estimateNeedsCap') }}</p>
              <p v-else class="nr__hint">{{ t('views.newRun.scope.estimateBasis', { agents: maxAgents, rounds }) }}</p>
            </div>
          </fieldset>

          <!-- Hinweise, Fehler, Fortschritt -->
          <div class="nr__status">
            <ul v-if="blockers.length > 0" class="nr__blockers" data-testid="new-run-blockers">
              <li v-for="b in blockers" :key="b">{{ b }}</li>
            </ul>
            <p v-if="busy" class="nr__progress" role="status" data-testid="new-run-progress">{{ phaseText }}</p>
            <p v-if="submit.error.value" class="nr__error" role="alert" data-testid="new-run-error">
              {{ submit.error.value }}
            </p>
            <RouterLink
              v-if="submit.createdSimulationId.value && submit.error.value"
              class="nr__link"
              data-testid="new-run-created-link"
              :to="{ name: 'RunOverview', params: { simulationId: submit.createdSimulationId.value } }"
            >
              {{ t('views.newRun.errors.openCreated') }}
            </RouterLink>
            <p v-if="uploadError" class="nr__error" role="alert">{{ uploadError }}</p>
          </div>

          <footer class="nr__footer">
            <button type="button" class="nr__btn" @click="close">{{ t('views.newRun.actions.cancel') }}</button>
            <div class="nr__create">
              <button
                type="button"
                class="nr__btn"
                :disabled="!canSubmit || graphMode !== 'existing'"
                :aria-describedby="graphMode === 'new' ? id('create-why') : undefined"
                data-testid="new-run-create-only"
                @click="onCreateOnly"
              >
                {{ t('views.newRun.actions.createOnly') }}
              </button>
              <p v-if="graphMode === 'new'" :id="id('create-why')" class="nr__hint">
                {{ t('views.newRun.actions.createOnlyWhy') }}
              </p>
            </div>
            <button
              type="submit"
              class="nr__btn nr__btn--primary"
              :disabled="!canSubmit"
              data-testid="new-run-start"
            >
              {{ startLabel }}
            </button>
          </footer>
        </form>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style scoped>
.nr-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: var(--scrim);
}

.nr {
  position: fixed;
  z-index: 201;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: min(760px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  display: flex;
  flex-direction: column;
  background: var(--s2);
  color: var(--fg);
  border-radius: var(--ag-r-16);
  box-shadow: var(--shadow-dlg);
  overflow: hidden;
  font-family: var(--ag-font-sans);
}

.nr__header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 16px 8px 24px;
}

.nr__title {
  flex: 1;
  margin: 0;
  font-size: 18px;
  font-weight: 650;
}

.nr__close {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--ag-r-8);
  background: transparent;
  color: var(--fg2);
  font: inherit;
  font-size: 15px;
  cursor: pointer;
}

.nr__close:hover {
  background: var(--s3);
}

.nr__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.nr__group {
  min-width: 0;
  margin: 0;
  padding: 12px 14px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.nr__legend {
  padding: 0 6px;
  font-size: 13.5px;
  font-weight: 650;
}

.nr__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.nr__row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.nr__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--fg2);
}

.nr__required {
  color: var(--status-error);
}

.nr__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.nr__textarea,
.nr__select,
.nr__number {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--field);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
}

.nr__textarea {
  resize: vertical;
}

.nr__textarea[readonly] {
  background: var(--s1);
  color: var(--fg2);
}

.nr__number {
  width: 120px;
}

.nr__textarea:focus-visible,
.nr__select:focus-visible,
.nr__number:focus-visible,
.nr__close:focus-visible,
.nr__btn:focus-visible,
.nr__link:focus-visible,
.nr__radio input:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}

.nr__radio {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.nr__radio input {
  margin-top: 3px;
}

.nr__radio-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13.5px;
}

.nr__radio--off .nr__radio-text > label {
  color: var(--fg2);
}

.nr__hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--fg2);
}

.nr__error {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--status-error);
  font-size: 13px;
}

.nr__status {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nr__blockers {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--fg2);
}

.nr__progress {
  margin: 0;
  font-size: 13px;
}

.nr__link {
  align-self: flex-start;
  color: var(--acc-text);
  font-size: 13px;
}

.nr__footer {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
}

.nr__footer > :first-child {
  margin-right: auto;
}

.nr__create {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 260px;
}

.nr__btn {
  height: 34px;
  padding: 0 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13.5px;
  cursor: pointer;
}

.nr__btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.nr__btn--primary {
  border-color: transparent;
  background: var(--acc);
  color: var(--on-acc);
}

@media (max-width: 767px) {
  .nr {
    width: calc(100vw - 16px);
    max-height: calc(100dvh - 16px);
  }

  .nr__body {
    padding: 8px 14px 16px;
  }

  .nr__row {
    flex-direction: column;
    gap: 12px;
  }

  .nr__number {
    width: 100%;
  }

  .nr__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .nr__footer > :first-child {
    margin-right: 0;
  }

  .nr__create {
    max-width: none;
  }
}
</style>
