<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { usePolling } from '../composables/usePolling'
import { usePersonaReview } from '../composables/usePersonaReview'
import { useI18n } from 'vue-i18n'
import {
  prepareSimulation,
  getPrepareStatus,
  getSimulationProfilesRealtime,
  getSimulationConfigRealtime,
  getAvailableModels,
  addSimulationProfile,
  deleteSimulationProfile,
  listPersonaTemplates,
  savePersonaTemplate,
  deletePersonaTemplate
} from '../api/simulation'
import Btn from './ui/Btn.vue'
import Badge from './ui/Badge.vue'
import Kicker from './ui/Kicker.vue'
import Field from './ui/Field.vue'
import Select from './ui/Select.vue'
import {
  PersonaQuotaPlanSchema,
  buildQuotaPlanFromEntries,
} from '../contracts/personaQuotaContract'

const { t } = useI18n()

const props = defineProps({
  simulationId: String,
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

// ----- Model + language picker (Phase 3 + 5) -----

const STORAGE_MODEL = 'agora.lastModel'
const STORAGE_LANG = 'agora.agentLanguage'

const ollamaModels = ref([])
const presetModels = ref([])
const defaultModel = ref('')
const ollamaReachable = ref(false)
const agentToolsEnabled = ref(false)
const maxToolCallsPerAction = ref(2)
const loadingModels = ref(true)
const modelOption = ref('default') // 'default' | preset name | 'custom'
const customModel = ref('')
const language = ref(localStorage.getItem(STORAGE_LANG) || 'de')

async function loadModels() {
  loadingModels.value = true
  try {
    const res = await getAvailableModels()
    if (res?.success) {
      ollamaModels.value = res.data?.ollama || []
      presetModels.value = res.data?.presets || []
      defaultModel.value = res.data?.current_default || ''
      ollamaReachable.value = !!res.data?.ollama_reachable
      agentToolsEnabled.value = !!res.data?.agent_tools_enabled
      maxToolCallsPerAction.value = res.data?.max_tool_calls_per_action || 2
      if (res.data?.default_language) {
        if (!localStorage.getItem(STORAGE_LANG)) language.value = res.data.default_language
      }
      const stored = localStorage.getItem(STORAGE_MODEL)
      if (stored && (
        stored === 'default' ||
        stored === 'custom' ||
        presetModels.value.some(p => p.name === stored) ||
        ollamaModels.value.some(p => p.name === stored)
      )) {
        modelOption.value = stored
      }
    }
  } catch (e) {
    addLog(t('errors.noLlm') + ' (' + e.message + ')')
  } finally {
    loadingModels.value = false
  }
}

const modelOptions = computed(() => {
  const opts = []
  opts.push({
    value: 'default',
    label: `${t('step2.model.default')} — ${defaultModel.value || '?'}`
  })
  for (const p of presetModels.value) {
    opts.push({ value: p.name, label: `${p.label || p.name}` })
  }
  for (const m of ollamaModels.value) {
    if (presetModels.value.some(p => p.name === m.name)) continue
    opts.push({ value: m.name, label: `${m.label || m.name} (Ollama)` })
  }
  opts.push({ value: 'custom', label: t('step2.model.customGroup') })
  return opts
})

watch(modelOption, (val) => {
  localStorage.setItem(STORAGE_MODEL, val)
})

watch(language, (val) => {
  localStorage.setItem(STORAGE_LANG, val)
})

function effectiveModel() {
  if (modelOption.value === 'default') return null
  if (modelOption.value === 'custom') return customModel.value.trim() || null
  return modelOption.value
}

// ----- Prepare flow -----

const phase = ref(0) // 0 idle, 1 personas, 2 config, 3 ready
const taskId = ref(null)
const prepareProgress = ref(0)
const progressMessage = ref('')
const profiles = ref([])
const expectedTotal = ref(null)
const simulationConfig = ref(null)
const useCustomRounds = ref(false)
const customMaxRounds = ref(40)
const useCustomDays = ref(false)
const customSimulationDays = ref(3)
const selectedProfile = ref(null)
const isPreparing = ref(false)
const personaSearch = ref('')
const showAllPersonas = ref(false)
const personaTemplates = ref([])
const isLoadingPersonaLibrary = ref(false)
const personaLibraryError = ref('')
const savingPersonaKeys = ref(new Set())
const usingPersonaTemplateIds = ref(new Set())

// Persona review (Slice 2.4): quality badges, approve/reject, inline edit.
const personaReview = usePersonaReview()
const editingProfile = ref(null) // editable working copy bound to the detail modal
const reviewActionPending = ref(false)
const reviewActionError = ref('')
const STATUS_VARIANTS = { approved: 'success', pending: 'warn', rejected: 'error' }
const SEVERITY_VARIANTS = { error: 'error', warning: 'warn', info: 'plasma' }
const STATUS_LABELS = { approved: 'freigegeben', pending: 'offen', rejected: 'abgelehnt' }

function statusVariant(status) {
  return STATUS_VARIANTS[status] || 'ghost'
}
function statusLabel(status) {
  return STATUS_LABELS[status] || status || '—'
}
function issueBadgeVariant(severity) {
  return SEVERITY_VARIANTS[severity] || 'ghost'
}
function startEditingSelected() {
  if (!selectedProfile.value) return
  const src = selectedProfile.value
  editingProfile.value = {
    username: src.username,
    name: src.name || '',
    bio: src.bio || '',
    persona: src.persona || '',
    profession: src.profession || '',
    country: src.country || '',
    age: src.age ?? null,
    gender: src.gender || 'other',
    mbti: src.mbti || '',
    interested_topics: Array.isArray(src.interested_topics)
      ? src.interested_topics.join(', ')
      : (src.interested_topics || ''),
  }
  reviewActionError.value = ''
}
function cancelEditing() {
  editingProfile.value = null
  reviewActionError.value = ''
}
function applyProfileToList(profile) {
  if (!profile?.username) return
  const idx = profiles.value.findIndex((p) => p.username === profile.username)
  if (idx >= 0) {
    profiles.value.splice(idx, 1, { ...profiles.value[idx], ...profile })
  }
  if (selectedProfile.value?.username === profile.username) {
    selectedProfile.value = { ...selectedProfile.value, ...profile }
  }
}
async function approveSelected() {
  if (!selectedProfile.value || !props.simulationId) return
  reviewActionPending.value = true
  reviewActionError.value = ''
  try {
    const data = await personaReview.approve(props.simulationId, selectedProfile.value.username)
    applyProfileToList(data?.profile)
    addLog(`Persona freigegeben: ${selectedProfile.value.username}`)
    await personaReview.refreshQuality(props.simulationId)
  } catch (err) {
    reviewActionError.value = err.message
  } finally {
    reviewActionPending.value = false
  }
}
async function rejectSelected() {
  if (!selectedProfile.value || !props.simulationId) return
  reviewActionPending.value = true
  reviewActionError.value = ''
  try {
    const data = await personaReview.reject(props.simulationId, selectedProfile.value.username)
    applyProfileToList(data?.profile)
    addLog(`Persona abgelehnt: ${selectedProfile.value.username}`)
    await personaReview.refreshQuality(props.simulationId)
  } catch (err) {
    reviewActionError.value = err.message
  } finally {
    reviewActionPending.value = false
  }
}
async function saveEditingProfile() {
  if (!editingProfile.value || !props.simulationId) return
  const payload = { ...editingProfile.value }
  delete payload.username
  if (typeof payload.interested_topics === 'string') {
    payload.interested_topics = payload.interested_topics
      .split(',').map((t) => t.trim()).filter(Boolean)
  }
  if (payload.age === '' || payload.age === null) delete payload.age
  reviewActionPending.value = true
  reviewActionError.value = ''
  try {
    const data = await personaReview.editProfile(
      props.simulationId,
      editingProfile.value.username,
      payload,
    )
    applyProfileToList(data?.profile)
    addLog(`Persona bearbeitet: ${editingProfile.value.username}`)
    editingProfile.value = null
    await personaReview.refreshQuality(props.simulationId)
  } catch (err) {
    reviewActionError.value = err.message
  } finally {
    reviewActionPending.value = false
  }
}

// Agent-count cap (optional; null = unlimited / all matching entities).
const STORAGE_MAX_AGENTS = 'agora.maxAgents'
const useAgentCap = ref(false)
const maxAgents = ref(Number(localStorage.getItem(STORAGE_MAX_AGENTS)) || 50)
watch(maxAgents, (v) => { localStorage.setItem(STORAGE_MAX_AGENTS, String(v)) })

// ----- Persona-Quota-Plan (Sub-Slice 20c, 24) -----
//
// Quoten erzwingen N Personas pro Segment, statt "1 Persona pro Entity".
// Backend-Pipeline (Sub-Slices 20a/20b/22): API-Pass-Through, Persistenz
// in simulation_config.json, Round-Robin-Expansion vor Phase 2.
//
// Sub-Slice 24 (Gemini-Followup auf 20c):
// - jeder Entry bekommt eine eigene `id` als v-for-Key (idx als Key
//   verursacht Fokus-Verlust beim Löschen mittlerer Zeilen)
// - i18n-Strings in step2.quota.*
const STORAGE_QUOTA_PLAN = 'agora.quotaPlan'
const useQuotaPlan = ref(false)
let _quotaEntryCounter = 0
function _newEntryId() {
  _quotaEntryCounter += 1
  return `q_${Date.now()}_${_quotaEntryCounter}`
}
function _loadQuotaEntries() {
  try {
    const raw = localStorage.getItem(STORAGE_QUOTA_PLAN)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || !parsed.targets) return []
    // Reihenfolge stabil halten — Object.entries macht insertion-order.
    return Object.entries(parsed.targets).map(([segment, count]) => ({
      id: _newEntryId(),
      segment,
      count: Number(count) || 1,
    }))
  } catch {
    return []
  }
}
const quotaEntries = ref(_loadQuotaEntries())
const quotaTotal = computed(() =>
  quotaEntries.value.reduce((acc, e) => acc + (Number(e.count) || 0), 0)
)
const quotaValidationError = computed(() => {
  if (!useQuotaPlan.value) return ''
  const plan = buildQuotaPlanFromEntries(quotaEntries.value)
  const result = PersonaQuotaPlanSchema.safeParse(plan)
  if (result.success) return ''
  // Erste Issue mit verständlicher Message
  const issue = result.error.issues[0]
  return issue?.message || t('step2.quota.invalid')
})
watch(
  quotaEntries,
  (entries) => {
    const plan = buildQuotaPlanFromEntries(entries)
    localStorage.setItem(STORAGE_QUOTA_PLAN, JSON.stringify(plan))
  },
  { deep: true }
)
function addQuotaSegment() {
  quotaEntries.value.push({ id: _newEntryId(), segment: '', count: 5 })
}
function removeQuotaSegment(idx) {
  quotaEntries.value.splice(idx, 1)
}

// Manual persona editor.
const showAddPersonaModal = ref(false)
const newPersona = ref({
  username: '', name: '', bio: '', persona: '',
  profession: '', country: 'DE', age: null, gender: 'other', mbti: '',
  interested_topics: ''
})
const isSavingPersona = ref(false)

function resetNewPersona() {
  newPersona.value = {
    username: '', name: '', bio: '', persona: '',
    profession: '', country: 'DE', age: null, gender: 'other', mbti: '',
    interested_topics: ''
  }
}

async function submitNewPersona() {
  if (!props.simulationId) return
  const data = { ...newPersona.value }
  // topics: comma-separated -> array
  if (typeof data.interested_topics === 'string') {
    data.interested_topics = data.interested_topics
      .split(',').map(s => s.trim()).filter(Boolean)
  }
  if (data.age === '' || data.age == null) delete data.age
  isSavingPersona.value = true
  try {
    const res = await addSimulationProfile(props.simulationId, data)
    if (res?.success) {
      addLog(`Persona hinzugefügt: ${res.data?.profile?.username}`)
      await fetchProfilesRealtime()
      showAddPersonaModal.value = false
      resetNewPersona()
    } else {
      addLog(`Fehler: ${res?.error || 'unbekannt'}`)
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    isSavingPersona.value = false
  }
}

function profileKey(profile) {
  return String(profile?.template_id || profile?.username || profile?.name || profile?.user_id || '')
}

function profilePayload(profile) {
  const payload = {}
  const fields = [
    'username', 'name', 'bio', 'persona', 'age', 'gender', 'mbti', 'country',
    'profession', 'interested_topics', 'source_entity_uuid', 'source_entity_type',
    'language', 'activity_level', 'time_zone', 'location', 'verified'
  ]
  for (const field of fields) {
    const value = profile?.[field]
    if (value !== undefined && value !== null && value !== '') payload[field] = value
  }
  return payload
}

async function loadPersonaLibrary() {
  isLoadingPersonaLibrary.value = true
  personaLibraryError.value = ''
  try {
    const res = await listPersonaTemplates()
    if (res?.success && Array.isArray(res.data?.templates)) {
      personaTemplates.value = res.data.templates
    } else {
      personaLibraryError.value = res?.error || 'Bibliothek konnte nicht geladen werden.'
    }
  } catch (err) {
    personaLibraryError.value = err.message
  } finally {
    isLoadingPersonaLibrary.value = false
  }
}

async function savePersona(profile) {
  const key = profileKey(profile)
  if (!key) return
  savingPersonaKeys.value = new Set([...savingPersonaKeys.value, key])
  try {
    const res = await savePersonaTemplate(profilePayload(profile))
    if (res?.success) {
      addLog(`Persona gespeichert: ${res.data?.template?.name || res.data?.template?.username || key}`)
      await loadPersonaLibrary()
    } else {
      addLog(`Fehler: ${res?.error || 'unbekannt'}`)
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    const next = new Set(savingPersonaKeys.value)
    next.delete(key)
    savingPersonaKeys.value = next
  }
}

async function saveAllPersonas() {
  for (const profile of profiles.value) {
    await savePersona(profile)
  }
}

async function usePersonaTemplate(template) {
  if (!props.simulationId || !template?.template_id) return
  usingPersonaTemplateIds.value = new Set([...usingPersonaTemplateIds.value, template.template_id])
  try {
    const payload = {
      ...profilePayload(template),
      source_entity_type: 'library',
    }
    const res = await addSimulationProfile(props.simulationId, payload)
    if (res?.success) {
      addLog(`Persona wiederverwendet: ${res.data?.profile?.username}`)
      await fetchProfilesRealtime()
    } else {
      addLog(`Fehler: ${res?.error || 'unbekannt'}`)
    }
  } catch (err) {
    addLog(err.message)
  } finally {
    const next = new Set(usingPersonaTemplateIds.value)
    next.delete(template.template_id)
    usingPersonaTemplateIds.value = next
  }
}

async function removePersonaTemplate(templateId) {
  if (!templateId) return
  if (!confirm('Gespeicherte Persona wirklich löschen?')) return
  try {
    const res = await deletePersonaTemplate(templateId)
    if (res?.success) await loadPersonaLibrary()
    else addLog(`Fehler: ${res?.error || 'unbekannt'}`)
  } catch (err) {
    addLog(err.message)
  }
}

async function removePersona(username) {
  if (!props.simulationId || !username) return
  if (!confirm(`Persona "${username}" löschen?`)) return
  try {
    const res = await deleteSimulationProfile(props.simulationId, username)
    if (res?.success) {
      addLog(`Persona gelöscht: ${username}`)
      await fetchProfilesRealtime()
    } else {
      addLog(`Fehler: ${res?.error || 'unbekannt'}`)
    }
  } catch (err) {
    addLog(err.message)
  }
}

const filteredPersonas = computed(() => {
  const q = personaSearch.value.trim().toLowerCase()
  if (!q) return profiles.value
  return profiles.value.filter((p) => {
    const hay = [
      p.username,
      p.name,
      p.bio,
      p.persona,
      p.profession,
      p.country,
      p.mbti,
      (p.interested_topics || []).join(' ')
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return hay.includes(q)
  })
})

const visiblePersonas = computed(() => {
  if (showAllPersonas.value || personaSearch.value.trim()) return filteredPersonas.value
  return filteredPersonas.value.slice(0, 24)
})

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

const prepareStatusPolling = usePolling(pollPrepareStatus, 2000)
const profilesPolling = usePolling(fetchProfilesRealtime, 3000)
const configPolling = usePolling(fetchConfigRealtime, 3000)

async function startPrepare() {
  if (!props.simulationId) {
    addLog(t('errors.unknown') + ': simulationId fehlt')
    emit('update-status', 'error')
    return
  }
  isPreparing.value = true
  phase.value = 1
  emit('update-status', 'processing')
  addLog(t('common.preparing'))
  try {
    const payload = {
      simulation_id: props.simulationId,
      use_llm_for_profiles: true,
      parallel_profile_count: 5,
      language: language.value,
    }
    const m = effectiveModel()
    if (m) payload.llm_model = m
    if (useAgentCap.value && maxAgents.value > 0) {
      payload.max_agents = maxAgents.value
    }
    // Sub-Slice 20c: PersonaQuotaPlan ans Backend durchreichen.
    // Client-seitige Validierung verhindert HTTP 400 für offensichtliche
    // Inkonsistenzen (total != sum, empty targets, count > 200).
    if (useQuotaPlan.value) {
      const plan = buildQuotaPlanFromEntries(quotaEntries.value)
      const validation = PersonaQuotaPlanSchema.safeParse(plan)
      if (!validation.success) {
        const msg = validation.error.issues[0]?.message || t('step2.quota.invalid')
        addLog(`${t('errors.personaGenFailed')}: ${msg}`)
        emit('update-status', 'error')
        isPreparing.value = false
        return
      }
      payload.quota_plan = plan
    }
    const res = await prepareSimulation(payload)
    if (res?.success && res.data) {
      if (res.data.already_prepared) {
        addLog(t('common.completed'))
        await loadPreparedData()
        return
      }
      taskId.value = res.data.task_id
      addLog(`Task: ${res.data.task_id}`)
      if (res.data.expected_entities_count) {
        expectedTotal.value = res.data.expected_entities_count
      }
      startPolling()
      startProfilesPolling()
    } else {
      addLog(`${t('errors.personaGenFailed')}: ${res?.error || ''}`)
      emit('update-status', 'error')
      isPreparing.value = false
    }
  } catch (err) {
    addLog(err.message)
    emit('update-status', 'error')
    isPreparing.value = false
  }
}

function startPolling() {
  void prepareStatusPolling.start()
}
function stopPolling() {
  prepareStatusPolling.stop()
}
function startProfilesPolling() {
  void profilesPolling.start()
}
function stopProfilesPolling() {
  profilesPolling.stop()
}
function startConfigPolling() {
  void configPolling.start()
}
function stopConfigPolling() {
  configPolling.stop()
}

async function pollPrepareStatus() {
  if (!taskId.value) return
  try {
    const res = await getPrepareStatus({ task_id: taskId.value })
    if (res?.success && res.data) {
      const st = res.data
      prepareProgress.value = st.progress || 0
      progressMessage.value = st.message || ''
      const stage = st.progress_detail?.current_stage
      if (stage === 'generating_config' && phase.value < 2) {
        phase.value = 2
        addLog('Konfiguration wird generiert…')
        startConfigPolling()
      }
      if (st.status === 'completed') {
        addLog(t('step2.personas.completed', { count: profiles.value.length }))
        stopPolling()
        stopProfilesPolling()
        stopConfigPolling()
        await loadPreparedData()
      } else if (st.status === 'failed') {
        addLog(`${t('errors.personaGenFailed')}: ${st.error || ''}`)
        stopPolling()
        stopProfilesPolling()
        stopConfigPolling()
        emit('update-status', 'error')
        isPreparing.value = false
      }
    }
  } catch (e) {
    console.warn(e)
  }
}

async function fetchProfilesRealtime() {
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    if (res?.success && Array.isArray(res.data?.profiles)) {
      profiles.value = res.data.profiles
      if (profiles.value.length) {
        // Refresh quality heuristics in the background; failures are reported
        // through personaReview.error and do not block the polling loop.
        personaReview.refreshQuality(props.simulationId)
      }
    }
  } catch { /* swallow */ }
}

async function fetchConfigRealtime() {
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res?.success && res.data?.config) {
      simulationConfig.value = res.data.config
    }
  } catch { /* swallow */ }
}

async function loadPreparedData() {
  await fetchProfilesRealtime()
  await fetchConfigRealtime()
  phase.value = 3
  emit('update-status', 'completed')
  isPreparing.value = false
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
    // Probe: if already prepared, just hydrate.
    fetchConfigRealtime().then(() => {
      if (simulationConfig.value) {
        loadPreparedData()
      }
    })
  }
})
onUnmounted(() => {
  stopPolling()
  stopProfilesPolling()
  stopConfigPolling()
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
          <!-- Model -->
          <div class="setup-cell">
            <Select
              v-model="modelOption"
              :label="t('step2.model.label')"
              :options="modelOptions"
            />
            <p class="hint" v-if="loadingModels">{{ t('step2.model.loadingModels') }}</p>
            <p class="hint" v-else-if="!ollamaReachable">{{ t('step2.model.noOllama') }}</p>
          </div>

          <!-- Custom model input (when 'custom' chosen) -->
          <div class="setup-cell" v-if="modelOption === 'custom'">
            <Field
              v-model="customModel"
              :label="t('step2.model.customLabel')"
              :placeholder="t('step2.model.customPlaceholder')"
            />
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
              <span>Max. Anzahl Agenten begrenzen</span>
            </label>
            <div v-if="useAgentCap" class="agent-cap-slider">
              <input
                type="range"
                v-model.number="maxAgents"
                min="5"
                max="500"
                step="5"
                :disabled="isPreparing"
              />
              <input
                type="number"
                v-model.number="maxAgents"
                min="1"
                max="2000"
                :disabled="isPreparing"
                class="agent-cap-number"
              />
              <span class="meta">Agenten</span>
            </div>
            <p class="hint" v-if="!useAgentCap">Ohne Begrenzung wird pro Entität im Graph ein Agent erzeugt.</p>
          </div>

          <!-- Persona-Quota-Plan (Sub-Slice 20c, 24): Soll-Counts pro Segment -->
          <div class="setup-cell setup-cell--wide">
            <label class="agent-cap">
              <input type="checkbox" v-model="useQuotaPlan" :disabled="isPreparing" />
              <span>{{ t('step2.quota.toggle') }}</span>
            </label>
            <p class="hint" v-if="!useQuotaPlan">{{ t('step2.quota.hintOff') }}</p>
            <div v-if="useQuotaPlan" class="quota-plan">
              <p class="hint">{{ t('step2.quota.hintOn') }}</p>
              <div
                v-for="(entry, idx) in quotaEntries"
                :key="entry.id"
                class="quota-row"
              >
                <input
                  type="text"
                  v-model.trim="entry.segment"
                  :placeholder="t('step2.quota.segmentPlaceholder')"
                  :disabled="isPreparing"
                  class="quota-segment"
                />
                <input
                  type="number"
                  v-model.number="entry.count"
                  min="1"
                  max="200"
                  :disabled="isPreparing"
                  class="quota-count"
                />
                <Btn
                  variant="ghost"
                  :disabled="isPreparing"
                  @click="removeQuotaSegment(idx)"
                >−</Btn>
              </div>
              <div class="quota-row">
                <Btn
                  variant="ghost"
                  :disabled="isPreparing"
                  @click="addQuotaSegment"
                >{{ t('step2.quota.addSegment') }}</Btn>
                <span class="meta">{{ t('step2.quota.total', { count: quotaTotal }) }}</span>
              </div>
              <p
                v-if="quotaValidationError"
                class="hint"
                style="color: var(--color-err, #d73a49)"
              >
                ⚠ {{ quotaValidationError }}
              </p>
            </div>
          </div>
        </div>

        <div class="actions">
          <Btn variant="ghost" @click="$emit('go-back')">← {{ t('common.back') }}</Btn>
          <Btn
            variant="primary"
            arrow
            :disabled="isPreparing"
            :loading="isPreparing && phase < 3"
            @click="startPrepare"
          >
            {{ phase === 0 ? t('step2.personas.generate') : t('common.processing') }}
          </Btn>
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

        <div class="personas-grid" v-if="visiblePersonas.length">
          <div
            v-for="(p, i) in visiblePersonas"
            :key="p.user_id || i"
            class="persona persona--card"
            :class="{ 'persona--manual': p.is_manual }"
          >
            <button
              class="persona-body"
              type="button"
              @click="selectedProfile = p"
            >
              <span class="persona-name">
                {{ p.name || p.username || 'agent_' + i }}
                <span v-if="p.username && p.name && p.username !== p.name" class="persona-handle">@{{ p.username }}</span>
                <span v-if="p.is_manual" class="persona-tag">manuell</span>
              </span>
              <span class="persona-meta-row">
                <Badge
                  v-if="p.review_status"
                  :variant="statusVariant(p.review_status)"
                  dot
                >{{ statusLabel(p.review_status) }}</Badge>
                <Badge
                  v-if="personaReview.getIssuesFor(p.username).length"
                  :variant="issueBadgeVariant(personaReview.highestSeverityFor(p.username))"
                >{{ personaReview.getIssuesFor(p.username).length }} Hinweis<span v-if="personaReview.getIssuesFor(p.username).length > 1">e</span></Badge>
              </span>
              <span class="persona-bio">{{ (p.bio || '').slice(0, 90) }}{{ (p.bio || '').length > 90 ? '…' : '' }}</span>
              <span v-if="p.interested_topics?.length" class="persona-topics">
                {{ p.interested_topics.slice(0, 3).join(' · ') }}
              </span>
            </button>
            <button
              class="persona-del"
              type="button"
              :title="'Persona löschen'"
              @click.stop="removePersona(p.username)"
            >×</button>
            <button
              class="persona-save"
              type="button"
              :title="t('step2.personas.save')"
              :disabled="savingPersonaKeys.has(profileKey(p))"
              @click.stop="savePersona(p)"
            >↧</button>
          </div>
        </div>

        <div v-if="phase >= 2" class="persona-actions">
          <Btn variant="ghost" @click="showAddPersonaModal = true">+ Persona hinzufügen</Btn>
          <Btn variant="ghost" :disabled="!profiles.length" @click="saveAllPersonas">
            {{ t('step2.personas.saveAll') }}
          </Btn>
        </div>
        <section v-if="phase >= 2" class="persona-library">
          <header class="persona-library-head">
            <div>
              <span class="kicker-mono">{{ t('step2.library.title') }}</span>
              <p class="meta">{{ t('step2.library.hint') }}</p>
            </div>
            <button class="persona-more-btn" type="button" :disabled="isLoadingPersonaLibrary" @click="loadPersonaLibrary">
              {{ t('step2.library.refresh') }}
            </button>
          </header>
          <p v-if="personaLibraryError" class="meta">{{ personaLibraryError }}</p>
          <div v-if="personaTemplates.length" class="persona-library-list">
            <article v-for="template in personaTemplates" :key="template.template_id" class="persona-template">
              <div>
                <strong>{{ template.name || template.username }}</strong>
                <span v-if="template.username" class="persona-handle">@{{ template.username }}</span>
                <p>{{ (template.bio || template.persona || '').slice(0, 120) }}{{ (template.bio || template.persona || '').length > 120 ? '…' : '' }}</p>
              </div>
              <div class="persona-template-actions">
                <button
                  type="button"
                  :disabled="usingPersonaTemplateIds.has(template.template_id)"
                  @click="usePersonaTemplate(template)"
                >
                  {{ t('step2.library.use') }}
                </button>
                <button type="button" @click="removePersonaTemplate(template.template_id)">×</button>
              </div>
            </article>
          </div>
          <p v-else class="meta">{{ t('step2.library.empty') }}</p>
        </section>
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
              <small class="meta">automatisch</small>
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
              <small class="meta">eigener Wert</small>
            </span>
          </label>
          <label class="rounds-radio">
            <input type="radio" :value="false" v-model="useCustomRounds" />
            <span>
              {{ t('step3.config.rounds') }}: {{ autoGeneratedRounds || '?' }}
              <small class="meta">automatisch</small>
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
              <small class="meta">eigener Wert</small>
            </span>
          </label>
        </div>

        <div class="actions">
          <Btn
            variant="primary"
            arrow
            :disabled="phase < 3"
            @click="handleStart"
          >
            {{ t('step3.controls.start') }}
          </Btn>
        </div>
      </article>
    </div>

    <!-- Modal: persona detail (editorial marginalia layout) -->
    <div v-if="selectedProfile" class="modal" @click.self="selectedProfile = null; cancelEditing()">
      <div class="modal-card">
        <header class="modal-head">
          <div>
            <div class="kicker-mono">№ Persona</div>
            <h3>{{ selectedProfile.name || selectedProfile.username }}</h3>
            <div v-if="selectedProfile.username && selectedProfile.name && selectedProfile.username !== selectedProfile.name" class="modal-handle">@{{ selectedProfile.username }}</div>
          </div>
          <button class="x" @click="selectedProfile = null; cancelEditing()" aria-label="×">×</button>
        </header>

        <div class="review-bar">
          <Badge
            v-if="selectedProfile.review_status"
            :variant="statusVariant(selectedProfile.review_status)"
            dot
          >{{ statusLabel(selectedProfile.review_status) }}</Badge>
          <span v-if="personaReview.reviewEnabled.value" class="meta">Review aktiv</span>
          <span class="review-bar-spacer" />
          <template v-if="!editingProfile">
            <Btn variant="ghost" :disabled="reviewActionPending" @click="startEditingSelected">Bearbeiten</Btn>
            <Btn
              variant="ghost"
              :disabled="reviewActionPending"
              @click="rejectSelected"
            >Ablehnen</Btn>
            <Btn
              variant="primary"
              :disabled="reviewActionPending"
              @click="approveSelected"
            >Freigeben</Btn>
          </template>
          <template v-else>
            <Btn variant="ghost" :disabled="reviewActionPending" @click="cancelEditing">Abbrechen</Btn>
            <Btn
              variant="primary"
              :loading="reviewActionPending"
              :disabled="reviewActionPending"
              @click="saveEditingProfile"
            >Speichern</Btn>
          </template>
        </div>

        <ul v-if="personaReview.getIssuesFor(selectedProfile.username).length" class="review-issues">
          <li
            v-for="issue in personaReview.getIssuesFor(selectedProfile.username)"
            :key="issue.code"
          >
            <Badge :variant="issueBadgeVariant(issue.severity)">{{ issue.severity }}</Badge>
            <span>{{ issue.code }}</span>
            <span v-if="issue.detail?.missing" class="meta">→ {{ issue.detail.missing.join(', ') }}</span>
          </li>
        </ul>
        <p v-if="reviewActionError" class="meta review-error">{{ reviewActionError }}</p>

        <template v-if="!editingProfile">
          <p class="modal-bio">{{ selectedProfile.bio }}</p>

          <div class="modal-marginalia">
            <dl>
              <div v-if="selectedProfile.age">
                <dt>Alter</dt>
                <dd>{{ selectedProfile.age }}</dd>
              </div>
              <div v-if="selectedProfile.gender">
                <dt>Gender</dt>
                <dd>{{ selectedProfile.gender }}</dd>
              </div>
              <div v-if="selectedProfile.mbti">
                <dt>MBTI</dt>
                <dd class="mono-big">{{ selectedProfile.mbti }}</dd>
              </div>
              <div v-if="selectedProfile.country">
                <dt>Land</dt>
                <dd>{{ selectedProfile.country }}</dd>
              </div>
              <div v-if="selectedProfile.profession">
                <dt>Beruf</dt>
                <dd>{{ selectedProfile.profession }}</dd>
              </div>
            </dl>
            <div class="modal-content">
              <div v-if="selectedProfile.interested_topics?.length" class="topic-chips">
                <span class="kicker-mono">{{ t('step5.agent.interests') }}</span>
                <div class="chips">
                  <span v-for="topic in selectedProfile.interested_topics" :key="topic" class="chip">
                    {{ topic }}
                  </span>
                </div>
              </div>
              <p class="modal-persona" v-if="selectedProfile.persona">
                {{ selectedProfile.persona }}
              </p>
            </div>
          </div>
        </template>

        <div v-else class="form-grid">
          <label class="form-row">
            <span>Anzeigename</span>
            <input v-model="editingProfile.name" type="text" />
          </label>
          <label class="form-row">
            <span>Beruf / Rolle</span>
            <input v-model="editingProfile.profession" type="text" />
          </label>
          <label class="form-row form-row--wide">
            <span>Bio (kurz)</span>
            <input v-model="editingProfile.bio" type="text" maxlength="200" />
          </label>
          <label class="form-row">
            <span>Land</span>
            <input v-model="editingProfile.country" type="text" maxlength="4" />
          </label>
          <label class="form-row">
            <span>Alter</span>
            <input v-model.number="editingProfile.age" type="number" min="15" max="99" />
          </label>
          <label class="form-row">
            <span>Gender</span>
            <select v-model="editingProfile.gender">
              <option value="other">other</option>
              <option value="female">female</option>
              <option value="male">male</option>
            </select>
          </label>
          <label class="form-row">
            <span>MBTI</span>
            <input v-model="editingProfile.mbti" type="text" maxlength="4" />
          </label>
          <label class="form-row form-row--wide">
            <span>Interessen (Komma-getrennt)</span>
            <input v-model="editingProfile.interested_topics" type="text" />
          </label>
          <label class="form-row form-row--wide">
            <span>Persona-Beschreibung</span>
            <textarea v-model="editingProfile.persona" rows="6" />
          </label>
        </div>
      </div>
    </div>

    <!-- Modal: add manual persona -->
    <div v-if="showAddPersonaModal" class="modal" @click.self="showAddPersonaModal = false">
      <div class="modal-card">
        <header class="modal-head">
          <div>
            <div class="kicker-mono">№ Neue Persona</div>
            <h3>Persona manuell anlegen</h3>
          </div>
          <button class="x" @click="showAddPersonaModal = false" aria-label="×">×</button>
        </header>

        <div class="form-grid">
          <label class="form-row">
            <span>Username *</span>
            <input v-model="newPersona.username" type="text" placeholder="z. B. kritische_buergerin" />
          </label>
          <label class="form-row">
            <span>Anzeigename</span>
            <input v-model="newPersona.name" type="text" placeholder="Anna Meyer" />
          </label>
          <label class="form-row form-row--wide">
            <span>Bio (kurz)</span>
            <input v-model="newPersona.bio" type="text" maxlength="150" placeholder="In einem Satz: wer und wofür." />
          </label>
          <label class="form-row">
            <span>Beruf / Rolle</span>
            <input v-model="newPersona.profession" type="text" placeholder="Stadtplanerin, Aktivist:in, …" />
          </label>
          <label class="form-row">
            <span>Land</span>
            <input v-model="newPersona.country" type="text" maxlength="4" placeholder="DE" />
          </label>
          <label class="form-row">
            <span>Alter</span>
            <input v-model.number="newPersona.age" type="number" min="15" max="99" />
          </label>
          <label class="form-row">
            <span>Gender</span>
            <select v-model="newPersona.gender">
              <option value="other">other</option>
              <option value="female">female</option>
              <option value="male">male</option>
            </select>
          </label>
          <label class="form-row">
            <span>MBTI</span>
            <input v-model="newPersona.mbti" type="text" maxlength="4" placeholder="INTJ" />
          </label>
          <label class="form-row form-row--wide">
            <span>Interessen (Komma-getrennt)</span>
            <input v-model="newPersona.interested_topics" type="text" placeholder="Überwachung, Datenschutz, Stadtpolitik" />
          </label>
          <label class="form-row form-row--wide">
            <span>Persona-Beschreibung (lang) — Haltung, Rhetorik, Milieu</span>
            <textarea v-model="newPersona.persona" rows="6" placeholder="Frei formuliert. Je konkreter, desto charakteristischer reagiert der Agent." />
          </label>
        </div>

        <div class="actions">
          <Btn variant="ghost" @click="showAddPersonaModal = false">Abbrechen</Btn>
          <Btn
            variant="primary"
            :loading="isSavingPersona"
            :disabled="!newPersona.username.trim() || isSavingPersona"
            @click="submitNewPersona"
          >Hinzufügen</Btn>
        </div>
      </div>
    </div>
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
.quota-plan {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.quota-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.quota-segment {
  flex: 1;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 4px 0;
  color: var(--fg);
  outline: none;
}
.quota-segment:focus { border-bottom-color: var(--accent); }
.quota-count {
  width: 70px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule-strong);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  padding: 4px 0;
  color: var(--fg);
  outline: none;
  text-align: right;
}
.quota-count:focus { border-bottom-color: var(--accent); }
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

.personas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--s-3);
}
.persona {
  border: 1px solid var(--rule);
  background: var(--bg-elevated);
  padding: var(--s-3);
  border-radius: var(--r-1);
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  text-align: left;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease;
}
.persona:hover { background: var(--bg-panel-2); border-color: var(--rule-strong); }

.persona--card {
  position: relative;
  padding: 0;
  cursor: default;
}
.persona--manual { border-color: var(--accent); }
.persona-body {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  padding: var(--s-3);
  background: transparent;
  border: 0;
  text-align: left;
  color: inherit;
  cursor: pointer;
  width: 100%;
}
.persona-del,
.persona-save {
  position: absolute;
  top: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid var(--rule);
  background: transparent;
  color: var(--fg-muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.persona-del { right: 6px; }
.persona-save {
  right: 34px;
  font-size: 13px;
}
.persona-del:hover,
.persona-save:hover {
  background: var(--accent);
  color: var(--accent-ink);
  border-color: var(--accent);
}
.persona-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin: var(--s-2) 0;
}
.review-bar {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  flex-wrap: wrap;
  padding: var(--s-3) 0;
  border-bottom: 1px solid var(--rule);
}
.review-bar-spacer { flex: 1; }
.review-issues {
  list-style: none;
  margin: var(--s-3) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.review-issues li {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--font-mono-sm);
  color: var(--fg-body);
}
.review-error {
  color: var(--status-error);
  margin-top: var(--s-2);
}
.persona-tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 9px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--accent-ink);
  letter-spacing: var(--ls-mono);
}
.persona-actions {
  display: flex;
  gap: var(--s-3);
  justify-content: flex-end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}

.persona-library {
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
}
.persona-library-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--s-3);
}
.persona-library-list {
  display: grid;
  gap: var(--s-2);
}
.persona-template {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--s-3);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-3);
  background: var(--bg-elevated);
}
.persona-template strong {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}
.persona-template p {
  margin: var(--s-1) 0 0;
  color: var(--fg-body);
}
.persona-template-actions {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}
.persona-template-actions button {
  border: 1px solid var(--rule);
  background: transparent;
  color: var(--fg);
  border-radius: var(--r-1);
  padding: 6px 8px;
  cursor: pointer;
}
.persona-template-actions button:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.persona-name {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.persona-bio {
  font-family: var(--ff-serif);
  font-size: var(--fs-16);
  line-height: 1.3;
  color: var(--fg);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-3);
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.form-row--wide { grid-column: 1 / -1; }
.form-row input,
.form-row select,
.form-row textarea {
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  color: var(--fg);
  font-family: var(--ff-sans);
  font-size: var(--fs-14);
  padding: 8px 10px;
  text-transform: none;
  letter-spacing: normal;
  outline: none;
}
.form-row textarea { resize: vertical; font-family: var(--ff-serif); line-height: 1.4; }
.form-row input:focus,
.form-row select:focus,
.form-row textarea:focus { border-color: var(--accent); }
@media (max-width: 640px) {
  .form-grid { grid-template-columns: 1fr; }
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

.persona-topics {
  display: block;
  margin-top: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--accent);
}

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

.modal {
  position: fixed; inset: 0;
  background: color-mix(in srgb, var(--bg) 60%, transparent);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  padding: var(--s-5);
}
.modal-card {
  background: var(--bg);
  border: 1px solid var(--rule-strong);
  padding: var(--s-7);
  max-width: 880px;
  max-height: 85vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  border-radius: var(--r-1);
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.kicker-mono {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: var(--s-2);
}
.modal-head h3 {
  font-family: var(--ff-serif);
  font-weight: 400;
  font-size: clamp(32px, 4vw, 52px);
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--fg);
}
.modal-bio {
  font-family: var(--ff-serif);
  font-style: italic;
  font-weight: 400;
  font-size: var(--fs-24);
  line-height: 1.35;
  color: var(--fg-body);
  margin: 0;
  border-left: 2px solid var(--accent);
  padding-left: var(--s-4);
}

.modal-marginalia {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: var(--s-7);
  border-top: 1px solid var(--rule);
  padding-top: var(--s-5);
}
.modal-marginalia dl {
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  margin: 0;
}
.modal-marginalia dt {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: 2px;
}
.modal-marginalia dd {
  margin: 0;
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  color: var(--fg);
}
.modal-marginalia dd.mono-big {
  font-family: var(--ff-mono);
  font-size: var(--fs-20);
  font-weight: 500;
  color: var(--accent);
}
.modal-content {
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}
.topic-chips { display: flex; flex-direction: column; gap: var(--s-2); }
.topic-chips .chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.topic-chips .chip {
  display: inline-block;
  padding: 4px 10px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  border: 1px solid var(--rule-strong);
  background: transparent;
  color: var(--fg);
  border-radius: var(--r-pill);
}
.modal-persona {
  white-space: pre-wrap;
  color: var(--fg-body);
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  line-height: 1.65;
  margin: 0;
}

@media (max-width: 720px) {
  .modal-marginalia { grid-template-columns: 1fr; }
}
.x {
  background: transparent;
  border: 0;
  font-size: 24px;
  cursor: pointer;
  color: var(--fg-muted);
}
.x:hover { color: var(--accent); }

@media (max-width: 720px) {
  .setup-grid { grid-template-columns: 1fr; }
}
</style>
