<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { chatWithReport, getReport } from '../api/report'
import { interviewAgents, getSimulationProfilesRealtime } from '../api/simulation'
import Btn from './ui/Btn.vue'
import Badge from './ui/Badge.vue'
import Kicker from './ui/Kicker.vue'
import Field from './ui/Field.vue'

const { t } = useI18n()

const props = defineProps({
  reportId: String,
  simulationId: String
})

const emit = defineEmits(['add-log', 'update-status'])

const activeTab = ref('chat') // 'chat' | 'survey'

const profiles = ref([])
const reportData = ref(null)

// ----- Chat (1-on-1) state -----
const selectedAgentId = ref(null) // null = ReportAgent
const search = ref('')
const chatHistory = ref([])
const chatInput = ref('')
const isSending = ref(false)
const messagesRef = ref(null)

// ----- Survey (batch) state -----
const surveySelected = ref(new Set())
const surveyQuestion = ref('')
const surveyResults = ref([]) // [{ agent_id, username, answer }]
const isSurveying = ref(false)
const surveyProgress = ref({ done: 0, total: 0 })
const surveySearch = ref('')

const filteredProfiles = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return profiles.value
  return profiles.value.filter((p) =>
    (p.username || '').toLowerCase().includes(q) ||
    (p.bio || '').toLowerCase().includes(q)
  )
})

const surveyFilteredProfiles = computed(() => {
  const q = surveySearch.value.trim().toLowerCase()
  if (!q) return profiles.value
  return profiles.value.filter((p) =>
    (p.username || '').toLowerCase().includes(q) ||
    (p.bio || '').toLowerCase().includes(q) ||
    (p.interested_topics || []).join(' ').toLowerCase().includes(q)
  )
})

const targetLabel = computed(() => {
  if (selectedAgentId.value === null) return t('step5.selectReport')
  const p = profiles.value[selectedAgentId.value]
  return p?.username || `agent_${selectedAgentId.value}`
})

const selectedProfile = computed(() => {
  if (selectedAgentId.value === null) return null
  return profiles.value[selectedAgentId.value]
})

async function loadProfiles() {
  if (!props.simulationId) return
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')
    if (res?.success && res.data?.profiles) profiles.value = res.data.profiles
  } catch (e) { /* swallow */ }
}

async function loadReport() {
  if (!props.reportId) return
  try {
    const res = await getReport(props.reportId)
    if (res?.success) reportData.value = res.data
  } catch (e) { /* swallow */ }
}

function pickAgent(idx) {
  selectedAgentId.value = idx
  chatHistory.value = []
}

function pickReportAgent() {
  selectedAgentId.value = null
  chatHistory.value = []
}

async function send() {
  const msg = chatInput.value.trim()
  if (!msg || isSending.value) return
  isSending.value = true
  chatHistory.value.push({ role: 'user', content: msg, ts: Date.now() })
  chatInput.value = ''
  scrollDown()
  try {
    if (selectedAgentId.value === null) {
      const res = await chatWithReport({
        simulation_id: props.simulationId,
        message: msg,
        chat_history: chatHistory.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content }))
      })
      if (res?.success) {
        chatHistory.value.push({
          role: 'assistant',
          content: res.data?.answer || res.data?.message || '',
          ts: Date.now()
        })
      }
    } else {
      const res = await interviewAgents({
        simulation_id: props.simulationId,
        interviews: [{ agent_id: selectedAgentId.value, prompt: msg }]
      })
      if (res?.success) {
        const result = (res.data?.results || res.data || [])[0]
        const answer = result?.answer || result?.response || result?.result || JSON.stringify(result)
        chatHistory.value.push({ role: 'assistant', content: answer, ts: Date.now() })
      }
    }
  } catch (err) {
    chatHistory.value.push({ role: 'assistant', content: `(${t('errors.network')}: ${err.message})`, ts: Date.now() })
  } finally {
    isSending.value = false
    scrollDown()
  }
}

function scrollDown() {
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })
}

function onKey(e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send()
}

// ----- Survey actions -----

function toggleSurveyAgent(idx) {
  const next = new Set(surveySelected.value)
  next.has(idx) ? next.delete(idx) : next.add(idx)
  surveySelected.value = next
}

function selectAllSurvey() {
  surveySelected.value = new Set(surveyFilteredProfiles.value.map((p, i) => profiles.value.indexOf(p)))
}

function clearSurvey() {
  surveySelected.value = new Set()
}

async function runSurvey() {
  const q = surveyQuestion.value.trim()
  if (!q || surveySelected.value.size === 0 || isSurveying.value) return
  isSurveying.value = true
  surveyResults.value = []
  const ids = Array.from(surveySelected.value)
  surveyProgress.value = { done: 0, total: ids.length }
  try {
    const res = await interviewAgents({
      simulation_id: props.simulationId,
      interviews: ids.map((id) => ({ agent_id: id, prompt: q }))
    })
    if (res?.success) {
      const arr = res.data?.results || res.data || []
      surveyResults.value = arr.map((r, i) => {
        const id = r.agent_id ?? ids[i]
        const p = profiles.value[id]
        return {
          agent_id: id,
          username: p?.username || `agent_${id}`,
          bio: p?.bio || '',
          answer: r.answer || r.response || r.result || JSON.stringify(r)
        }
      })
      surveyProgress.value = { done: arr.length, total: ids.length }
    }
  } catch (err) {
    surveyResults.value = [{ agent_id: -1, username: '–', answer: `(${t('errors.network')}: ${err.message})` }]
  } finally {
    isSurveying.value = false
  }
}

function exportCsv() {
  if (!surveyResults.value.length) return
  const rows = [
    ['agent_id', 'username', 'question', 'answer'],
    ...surveyResults.value.map((r) => [r.agent_id, r.username, surveyQuestion.value, r.answer])
  ]
  const csv = rows
    .map((row) =>
      row.map((cell) => '"' + String(cell ?? '').replace(/"/g, '""') + '"').join(',')
    )
    .join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `agora-survey-${Date.now()}.csv`
  a.click()
}

onMounted(async () => {
  await Promise.all([loadProfiles(), loadReport()])
})
</script>

<template>
  <div class="step-panel">
    <!-- Tab switcher -->
    <nav class="tabs">
      <button class="tab" :class="{ active: activeTab === 'chat' }" @click="activeTab = 'chat'">
        {{ t('step5.tabs.chat') }}
      </button>
      <button class="tab" :class="{ active: activeTab === 'survey' }" @click="activeTab = 'survey'">
        {{ t('step5.tabs.survey') }}
      </button>
    </nav>

    <!-- ===== Chat tab ===== -->
    <div v-if="activeTab === 'chat'" class="layout">
      <aside class="picker">
        <Kicker num="01">{{ t('step5.selectAgent') }}</Kicker>

        <button
          class="agent-row"
          :class="{ active: selectedAgentId === null }"
          @click="pickReportAgent"
        >
          <span class="dot accent" />
          <span class="agent-name">{{ t('step5.selectReport') }}</span>
        </button>

        <Field v-model="search" :label="t('step5.search')" :placeholder="t('step5.search')" />

        <div class="agent-scroll">
          <button
            v-for="(p, i) in filteredProfiles"
            :key="p.user_id || i"
            class="agent-row"
            :class="{ active: selectedAgentId === profiles.indexOf(p) }"
            @click="pickAgent(profiles.indexOf(p))"
          >
            <span class="dot" />
            <span class="agent-name">{{ p.username || ('agent_' + i) }}</span>
            <span class="agent-bio">{{ (p.bio || '').slice(0, 60) }}</span>
          </button>
        </div>
      </aside>

      <section class="chat">
        <header class="chat-head">
          <div>
            <Kicker num="02">{{ t('step5.title') }}</Kicker>
            <h2 class="target">{{ targetLabel }}</h2>
          </div>
          <Badge :variant="selectedAgentId === null ? 'accent' : 'ghost'">
            {{ selectedAgentId === null ? 'ReportAgent' : 'Agent' }}
          </Badge>
        </header>

        <div ref="messagesRef" class="messages">
          <div v-if="!chatHistory.length" class="empty">{{ t('step5.empty') }}</div>
          <div
            v-for="(m, i) in chatHistory"
            :key="i"
            class="msg"
            :class="m.role"
          >
            <span class="role">{{ m.role === 'user' ? 'Du' : targetLabel }}</span>
            <p class="body">{{ m.content }}</p>
          </div>
          <div v-if="isSending" class="msg assistant">
            <span class="role">{{ targetLabel }}</span>
            <p class="body meta">{{ t('common.thinking') }}</p>
          </div>
        </div>

        <div class="composer">
          <textarea
            v-model="chatInput"
            class="input"
            :placeholder="t('step5.input.placeholder')"
            rows="3"
            @keydown="onKey"
          />
          <Btn variant="primary" arrow :loading="isSending" @click="send">
            {{ t('step5.input.send') }}
          </Btn>
        </div>

        <details v-if="selectedProfile" class="profile-card">
          <summary>{{ t('step5.agent.bio') }} · {{ targetLabel }}</summary>
          <p class="profile-bio">{{ selectedProfile.bio }}</p>
          <p class="profile-persona" v-if="selectedProfile.persona">{{ selectedProfile.persona }}</p>
        </details>
      </section>
    </div>

    <!-- ===== Survey tab ===== -->
    <div v-else class="layout">
      <aside class="picker">
        <Kicker num="01">{{ t('step5.selectAgent') }}</Kicker>
        <Field v-model="surveySearch" :label="t('step5.search')" :placeholder="t('step5.search')" />
        <div class="picker-actions">
          <Btn variant="ghost" @click="selectAllSurvey">{{ t('step5.survey.selectAll') }}</Btn>
          <Btn variant="ghost" @click="clearSurvey">{{ t('step5.survey.clear') }}</Btn>
        </div>
        <p class="meta">{{ t('step5.survey.selected', { count: surveySelected.size }) }}</p>
        <div class="agent-scroll">
          <label
            v-for="p in surveyFilteredProfiles"
            :key="p.user_id || profiles.indexOf(p)"
            class="agent-check"
            :class="{ active: surveySelected.has(profiles.indexOf(p)) }"
          >
            <input
              type="checkbox"
              :checked="surveySelected.has(profiles.indexOf(p))"
              @change="toggleSurveyAgent(profiles.indexOf(p))"
            />
            <span class="agent-name">{{ p.username || ('agent_' + profiles.indexOf(p)) }}</span>
            <span class="agent-bio">{{ (p.bio || '').slice(0, 50) }}</span>
          </label>
        </div>
      </aside>

      <section class="chat">
        <header class="chat-head">
          <div>
            <Kicker num="02" accent>{{ t('step5.tabs.survey') }}</Kicker>
            <h2 class="target">{{ t('step5.survey.title') }}</h2>
            <p class="sub">{{ t('step5.survey.sub') }}</p>
          </div>
          <Badge :variant="isSurveying ? 'accent' : 'ghost'" :dot="isSurveying">
            {{ isSurveying ? t('step5.survey.asking', surveyProgress) : (surveyResults.length + ' / ' + surveySelected.size) }}
          </Badge>
        </header>

        <div class="survey-question">
          <Field
            v-model="surveyQuestion"
            :label="t('step5.survey.question')"
            :placeholder="t('step5.survey.placeholder')"
          />
          <div class="survey-actions">
            <Btn
              variant="primary"
              arrow
              :loading="isSurveying"
              :disabled="!surveyQuestion.trim() || surveySelected.size === 0"
              @click="runSurvey"
            >
              {{ t('step5.survey.ask') }}
            </Btn>
            <Btn
              v-if="surveyResults.length"
              variant="ghost"
              @click="exportCsv"
            >{{ t('step5.survey.exportCsv') }}</Btn>
          </div>
        </div>

        <div class="survey-results">
          <div v-if="!surveyResults.length && !isSurveying" class="empty">
            {{ t('step5.survey.noResults') }}
          </div>
          <article v-for="(r, i) in surveyResults" :key="i" class="survey-row">
            <header class="survey-row-head">
              <span class="meta">{{ String(i + 1).padStart(2, '0') }}</span>
              <span class="survey-name">{{ r.username }}</span>
            </header>
            <p class="survey-bio meta" v-if="r.bio">{{ r.bio.slice(0, 120) }}</p>
            <p class="survey-answer">{{ r.answer }}</p>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.step-panel {
  height: 100%;
  background: var(--paper-0);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--rule-strong);
  padding: 0 var(--s-5);
}
.tab {
  background: transparent;
  border: 0;
  padding: var(--s-4) var(--s-5);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab:hover { color: var(--ink-0); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.layout {
  flex: 1;
  display: grid;
  grid-template-columns: 320px 1fr;
  overflow: hidden;
}

.picker {
  border-right: 1px solid var(--rule);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  overflow: hidden;
}
.picker-actions { display: flex; gap: var(--s-2); }
.agent-scroll {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: var(--s-3);
}
.agent-row {
  display: grid;
  grid-template-columns: 14px 1fr;
  gap: var(--s-2);
  padding: var(--s-3);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--rule);
  text-align: left;
  cursor: pointer;
  transition: background 150ms ease;
}
.agent-row:hover { background: var(--paper-1); }
.agent-row.active { background: var(--paper-1); border-left: 2px solid var(--accent); padding-left: calc(var(--s-3) - 2px); }
.agent-row .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ink-3); margin-top: 6px; }
.agent-row .dot.accent { background: var(--accent); }
.agent-name {
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  color: var(--ink-0);
  letter-spacing: 0.02em;
}
.agent-bio {
  grid-column: 2;
  font-family: var(--ff-sans);
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-check {
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: var(--s-2);
  padding: var(--s-3);
  border-bottom: 1px solid var(--rule);
  cursor: pointer;
  transition: background 150ms ease;
  align-items: center;
}
.agent-check:hover { background: var(--paper-1); }
.agent-check.active { background: var(--paper-1); border-left: 2px solid var(--accent); padding-left: calc(var(--s-3) - 2px); }
.agent-check input[type="checkbox"] { accent-color: var(--accent); cursor: pointer; }

.chat {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: var(--s-5);
  gap: var(--s-4);
}
.chat-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.target {
  font-family: var(--ff-serif);
  font-weight: 400;
  font-size: var(--fs-32);
  color: var(--ink-0);
  margin: var(--s-2) 0 0;
}
.sub {
  font-family: var(--ff-sans);
  color: var(--fg-body);
  font-size: var(--fs-14);
  margin: var(--s-2) 0 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
  padding: var(--s-3) 0;
}
.empty {
  text-align: center;
  color: var(--fg-muted);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  padding: var(--s-9) 0;
}
.msg .role {
  display: block;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--s-2);
}
.msg .body {
  font-family: var(--ff-serif);
  font-size: var(--fs-18);
  line-height: 1.55;
  color: var(--ink-0);
  margin: 0;
  white-space: pre-wrap;
}
.msg.user .body { color: var(--accent); }

.composer {
  display: flex;
  gap: var(--s-3);
  align-items: flex-end;
  border-top: 1px solid var(--rule);
  padding-top: var(--s-3);
}
.input {
  flex: 1;
  background: var(--paper-1);
  border: 1px solid var(--rule);
  padding: var(--s-3);
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  color: var(--ink-0);
  resize: vertical;
  outline: none;
  border-radius: var(--r-1);
}
.input:focus { border-color: var(--accent); }

.profile-card {
  background: var(--paper-1);
  border: 1px solid var(--rule);
  padding: var(--s-3);
  border-radius: var(--r-1);
}
.profile-card summary {
  cursor: pointer;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.profile-bio {
  font-family: var(--ff-serif);
  font-style: italic;
  font-size: var(--fs-18);
  color: var(--ink-3);
  margin: var(--s-3) 0 0;
}
.profile-persona {
  white-space: pre-wrap;
  font-size: var(--fs-14);
  line-height: 1.55;
  color: var(--fg-body);
  margin: var(--s-3) 0 0;
}

/* Survey */
.survey-question {
  border: 1px solid var(--rule);
  padding: var(--s-4);
  border-radius: var(--r-1);
  display: flex;
  flex-direction: column;
  gap: var(--s-3);
  background: var(--paper-1);
}
.survey-actions { display: flex; gap: var(--s-3); align-self: flex-end; }
.survey-results {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.survey-row {
  border-top: 1px solid var(--rule);
  padding: var(--s-4) 0;
}
.survey-row:last-child { border-bottom: 1px solid var(--rule); }
.survey-row-head {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
  margin-bottom: var(--s-2);
}
.survey-name {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--ink-0);
}
.survey-bio { display: block; margin-bottom: var(--s-2); font-style: italic; }
.survey-answer {
  font-family: var(--ff-serif);
  font-size: var(--fs-18);
  line-height: 1.55;
  color: var(--ink-0);
  margin: 0;
  white-space: pre-wrap;
}

@media (max-width: 720px) {
  .layout { grid-template-columns: 1fr; }
  .picker { border-right: none; border-bottom: 1px solid var(--rule); max-height: 280px; }
}
</style>
