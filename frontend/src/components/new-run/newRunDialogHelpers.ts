import { computed, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { fetchLlmProfiles } from '@/api/llmProfiles'
import { preflightEstimate } from '@/api/budget'
import type { PreflightEstimateParams } from '@/api/budget'
import { getAvailableModels } from '@/api/simulation'
import { setPendingUpload } from '@/store/pendingUpload'
import { clearRunModelOverride, setRunModelOverride } from '@/store/runModelOverride'
import { toRunParamsQuery, MAX_SIMULATION_DAYS } from '@/contracts/runParamsQuery'
import { MIN_SIMULATION_AGENTS } from '@/constants/personaFloor'
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

// ---- Grenzen (wie im Bestand von HeroNewRun / Schritt 2) ----
// Untergrenze der Personas-Obergrenze: geteilter Spiegel der Backend-Konstante
// MIN_SIMULATION_AGENTS (siehe constants/personaFloor.ts). Eine kleinere
// Obergrenze ist bewusst zulässig — sie senkt den wirksamen Report-Floor.
export const MIN_AGENTS = MIN_SIMULATION_AGENTS
export const DEFAULT_AGENTS = 30
export const MIN_ROUNDS = 3
export const MAX_ROUNDS = 30
export const DEFAULT_ROUNDS = 24
export const DEFAULT_DAYS = 1
export const CONTESTED_MIN = 10
export const CONTESTED_MAX = 300
export const STORAGE_PROFILE_ID = 'agora.hero.profileId'

export type GraphMode = 'existing' | 'new'
export type PersonaMode = 'generate' | 'set'

// ---- Speicher-Helfer ----
export function readLocal(key: string): string | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage?.getItem(key) ?? null
  } catch {
    return null
  }
}

export function writeLocal(key: string, value: string | null): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    /* Speicher gesperrt: die Auswahl gilt nur für diesen Dialog. */
  }
}

export function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('de-DE')
}

export function graphLabel(g: { name: string; updatedAt: string; question: string | null }): string {
  const q = g.question ? ` — ${g.question.length > 70 ? `${g.question.slice(0, 70)}…` : g.question}` : ''
  return `${g.name} (${formatDate(g.updatedAt)})${q}`
}

export function useNewRunDialogState() {
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

  // ---- Gruppe 1: Frage ----
  const question = ref('')
  const contestedQuestion = ref('')

  // ---- Gruppe 2: Graph ----
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

  return {
    t,
    id,
    operatorAccess,
    question,
    contestedQuestion,
    graphMode,
    selectedProjectId,
    files,
    documentRoles,
    fileError,
    graphsSource,
    personaMode,
    personaSets,
    selectedPersonaSetId,
    selectedPersonaSet,
    personaSetUsable,
    existingGraphs,
    useAgentCap,
    maxAgents,
    selectedProfileId,
    selectedModel,
    language,
    profileOptions,
    onPickProfile,
    onPickModel,
    days,
    rounds,
    activityMode,
    budgetDefaults,
    budget,
    budgetChanged,
    onBudgetUpdate,
    estimate,
    estimateLoading,
    estimateError,
    refreshEstimate,
    submit,
    uploadError,
    busy,
    agentsValid,
    daysValid,
    roundsValid,
    blockers,
    canSubmit,
    onCreateOnly,
    onStart,
    close,
    restoreFocus,
    questionText,
    phaseText,
    startLabel,
  }
}
