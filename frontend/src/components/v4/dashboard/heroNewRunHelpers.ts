import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { fetchLlmProfiles } from '../../../api/llmProfiles'
import { preflightEstimate } from '../../../api/budget'
import type { PreflightEstimateParams } from '../../../api/budget'
import { setPendingUpload } from '../../../store/pendingUpload'
import { toRunParamsQuery } from '../../../contracts/runParamsQuery'
import { DocumentRoleSchema, type DocumentRole } from '../../../contracts/documentRoleContract'
import { STORAGE_LANG } from '../../../composables/useEnvForm'
import { useEffectiveModelSelection } from '@/composables/useEffectiveModelSelection'
import { useOperatorAccess } from '@/composables/useOperatorAccess'
import { setRunModelOverride, clearRunModelOverride } from '@/store/runModelOverride'
import type { LlmProfile } from '../../../contracts/llmProfileContract'
import type { AiModelRef } from '@/contracts/aiModelRef'
import type {
  PreflightEstimate,
  RunBudgetConfig,
} from '../../../contracts/runBudgetContract'
import { getAvailableModels } from '../../../api/simulation'

export const ALLOWED = ['.pdf', '.md', '.txt', '.markdown']

// Issue #1240: Textsorte je Datei, positionsgleich zu `files`. Szenario-,
// Frage- und Erwartungstext stützen im Report keinen Claim — sonst liest der
// Report die mitgelieferten Antworten als Simulationsbefund. Positionen statt
// Dateinamen, weil zwei Uploads gleich heißen können (Codex-Review PR #1606).
export const DOCUMENT_ROLES = DocumentRoleSchema.options

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
 * `agora.run.aiModelRefOverride` (store/runModelOverride), die die Steuerung der
 * Simulation (useSimulationControl) beim Sim-Start vorrangig vor dem Kanon als `ai_model_ref` sendet.
 * Slice 7.6c (Storage-Cut): Der Legacy-Key `agora.hero.route` wird
 * NICHT mehr gelesen und beim Mount defensiv entfernt.
 */
export const STORAGE_HERO_PROFILE_ID = 'agora.hero.profileId'
// Slice 7.6c (Storage-Cut): nur noch als Ziel für defensives removeLocal.
export const STORAGE_HERO_ROUTE_LEGACY = 'agora.hero.route'

// Die harte Untergrenze von 30 Personas ist entfallen (Block B4): sie
// stand kleinen, gezielten Laeufen im Weg — etwa einem Gremium aus acht
// Leuten. 30 bleibt der Vorschlag, ist aber keine Schranke mehr.
export const NUM_AGENTS_MIN = 1
export const NUM_AGENTS_DEFAULT = 30
export const NUM_AGENTS_MAX = 100
export const NUM_ROUNDS_MIN = 3
export const NUM_ROUNDS_DEFAULT = 10
export const NUM_ROUNDS_MAX = 30

export function readLocal(key: string): string | null {
  try {
    if (typeof window === 'undefined') return null
    const ls = window.localStorage
    if (!ls || typeof ls.getItem !== 'function') return null
    return ls.getItem(key)
  } catch {
    return null
  }
}

export function writeLocal(key: string, value: string): void {
  try {
    if (typeof window === 'undefined') return
    const ls = window.localStorage
    if (!ls || typeof ls.setItem !== 'function') return
    ls.setItem(key, value)
  } catch { /* swallow */ }
}

export function removeLocal(key: string): void {
  try {
    if (typeof window === 'undefined') return
    const ls = window.localStorage
    if (!ls || typeof ls.removeItem !== 'function') return
    ls.removeItem(key)
  } catch { /* swallow */ }
}

export function filterAllowed(list: FileList | File[]): File[] {
  return Array.from(list).filter(f => {
    const lower = f.name.toLowerCase()
    return ALLOWED.some(ext => lower.endsWith(ext))
  })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function useHeroNewRunState() {
  const { t } = useI18n()
  const router = useRouter()

  const files = ref<File[]>([])
  const documentRoles = ref<DocumentRole[]>([])
  const isDragOver = ref(false)
  const fileInput = ref<HTMLInputElement | null>(null)
  const errorMsg = ref('')

  const llmProfiles = ref<LlmProfile[]>([])
  // Solange der Profilabruf laeuft, ist unbekannt ob eine persistierte
  // `agora.hero.profileId` noch existiert. Der Start bleibt bis dahin zu —
  // sonst geht eine tote ID als profile_id raus und der Sim-Start bricht mit
  // "LLM-Profil ... nicht gefunden" ab.
  const profilesSettled = ref(false)

  // Neo4j ist eine gemeinsame Run-Abhängigkeit. Die globale Ollama-Probe
  // beschreibt dagegen weder das Profil noch die gewählte Provider-Connection.
  const neo4jReachable = ref<boolean>(false)

  // Phase-1 Konsolidierung: Default-Modell kommt aus dem Kanon
  // (routing/defaults.global via useEffectiveModelSelection), nicht mehr aus
  // einem eigenen localStorage-Key.
  const effectiveModel = useEffectiveModelSelection()
  const operatorAccess = useOperatorAccess()

  const selectedProfileId = ref<string | null>(readLocal(STORAGE_HERO_PROFILE_ID))
  const selectedModel = ref<AiModelRef | null>(null)
  // Run-Override nur bei explizitem Picker-Pick schreiben: selectedModel wird
  // beim Mount aus dem Kanon initialisiert und darf den Kanon nicht als
  // Override festschreiben — spätere Kanon-Änderungen sollen bis zum Sim-Start
  // durchschlagen (Review-Finding PR #853).
  const hasExplicitPick = ref(false)
  const language = ref<string>(readLocal(STORAGE_LANG) || 'de')
  const simulationRequirement = ref('')

  const numAgents = ref<number>(NUM_AGENTS_DEFAULT)
  const numRounds = ref<number>(NUM_ROUNDS_DEFAULT)

  // ---- Issue #764: optionale Run-Budgets + Preflight-Schätzung ----
  // Das Budget wandert über die Route-Query (contracts/runParamsQuery) zu
  // die Steuerung der Simulation (useSimulationControl, via pendingRunParams), die es beim Sim-Start als `budget` an
  // /api/simulation/start durchreicht. Nicht über den pendingUpload-Store: den
  // leert Schritt 1 nach dem Upload, das Budget kam nie an (Issue #1234). Die
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

  const numAgentsMin = computed<number>(() => NUM_AGENTS_MIN)

  // Unter 30 Personas wird die Aussagekraft duenn — das ist ein Hinweis,
  // keine Sperre.
  const showAgentsWarning = computed<boolean>(() => numAgents.value < 30)

  const profileOptions = computed(() => {
    return llmProfiles.value.map(p => ({
      value: p.id,
      label: `${p.name} — ${p.model_name}${p.is_default ? ` (${t('dashboard.hero.profileDefault')})` : ''}`,
    }))
  })

  // Modellrouten werden beim Ausführen im Backend aufgelöst. Ein veralteter
  // Server-Default darf Cloud-Profile, Kanon-Defaults oder andere Ollama-
  // Connections nicht sperren; die globale Probe bleibt reine Statusinformation.
  const servicesReady = computed(() => neo4jReachable.value)

  // Workspace-Sessions haben keinen lesbaren Kanon-Default: ohne expliziten
  // Picker-Pick liefe der Lauf über den globalen Default der Demo, für den der
  // Workspace womöglich keinen Key hat (#1688). Daher Pflichtauswahl.
  const workspaceModelMissing = computed(
    () => !operatorAccess.value && !(hasExplicitPick.value && selectedModel.value),
  )

  const canSubmit = computed(
    () =>
      files.value.length > 0 &&
      simulationRequirement.value.trim() !== '' &&
      servicesReady.value &&
      profilesSettled.value &&
      !workspaceModelMissing.value,
  )

  const disabledHint = computed(() => {
    if (!files.value.length || !simulationRequirement.value.trim()) return t('dashboard.hero.disabledHint')
    if (!servicesReady.value) return t('dashboard.hero.servicesUnavailableHint')
    if (workspaceModelMissing.value) return t('dashboard.hero.workspaceModelRequiredHint')
    return t('dashboard.hero.profilesLoadingHint')
  })

  function discardPersistedProfile() {
    selectedProfileId.value = null
    removeLocal(STORAGE_HERO_PROFILE_ID)
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
    documentRoles.value = [
      ...documentRoles.value,
      ...accepted.map((): DocumentRole => 'domain_fact'),
    ]
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
    documentRoles.value.splice(i, 1)
  }

  function onPickRole(index: number, event: Event) {
    const parsed = DocumentRoleSchema.safeParse((event.target as HTMLSelectElement).value)
    if (parsed.success) documentRoles.value[index] = parsed.data
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
        // Run-Override: die Steuerung der Simulation sendet ihn beim Sim-Start vorrangig
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
        files.value.map((_file, index) => documentRoles.value[index] ?? 'domain_fact'),
      )
      // Rundenzahl und Budget gehen in die Query, nicht in den Store: Schritt 1
      // leert ihn nach dem Upload (`clearPendingUpload`), Schritt 3 las danach
      // Reset-Defaults — die eingestellte Rundenzahl wurde still zu 10, das
      // Budget verschwand ganz (Issue #1234). Die Dateien bleiben zwangsläufig
      // im Store, sie sind nicht serialisierbar.
      router.push({
        name: 'Process',
        params: { projectId: 'new' },
        query: toRunParamsQuery({ maxRounds: numRounds.value, budget: budget.value }),
      })
    } catch (e) {
      errorMsg.value = e instanceof Error ? e.message : String(e)
    }
  }

  onMounted(() => {
    // Slice 7.6c (Storage-Cut): Legacy-Route-Key einmalig defensiv entsorgen.
    removeLocal(STORAGE_HERO_ROUTE_LEGACY)
    // Phase-1 Konsolidierung: Default-Modell aus dem Kanon initialisieren, damit
    // der Dashboard-Start dieselbe Auswahl wie Settings zeigt.
    if (!operatorAccess.value) {
      // Workspace-Sessions dürfen prozessweite Profile und Defaults nicht lesen.
      // Die Auswahl erfolgt im JWT-sicheren Picker als Run-Override.
      discardPersistedProfile()
      profilesSettled.value = true
    } else {
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
            discardPersistedProfile()
          }
        })
        .catch(() => {
          // Ohne Liste laesst sich die persistierte ID nicht verifizieren. Sie
          // trotzdem zu senden waere geraten — der ModelPicker-Pfad greift.
          discardPersistedProfile()
        })
        .finally(() => { profilesSettled.value = true })
    }
    // Neo4j-Readiness + Backend-Default-Language. Bei Fetch-Fehler bleibt
    // Neo4j pessimistisch auf false, bis die Bereitschaft bestätigt ist.
    getAvailableModels()
      .then(res => {
        const data = (res?.data ?? {}) as {
          neo4j_reachable?: boolean
          default_language?: string
        }
        if (!res?.success) return
        neo4jReachable.value = !!data.neo4j_reachable
        if (data.default_language && !readLocal(STORAGE_LANG)) {
          language.value = data.default_language
        }
      })
      .catch(() => { /* Fail-safe: servicesReady bleibt false → Submit blockt */ })
  })

  return {
    files,
    documentRoles,
    isDragOver,
    fileInput,
    errorMsg,
    operatorAccess,
    selectedProfileId,
    selectedModel,
    language,
    simulationRequirement,
    numAgents,
    numRounds,
    budget,
    estimate,
    estimateLoading,
    estimateError,
    refreshEstimate,
    numAgentsMin,
    showAgentsWarning,
    profileOptions,
    canSubmit,
    disabledHint,
    onPickClick,
    onPickKey,
    onFiles,
    onDrop,
    onDragOver,
    onDragLeave,
    removeFile,
    onPickRole,
    onPickModel,
    onPickProfile,
    startSimulation,
  }
}
