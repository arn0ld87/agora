<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import AppFooter from '../components/AppFooter.vue'
import Btn from '../components/ui/Btn.vue'
import Badge from '../components/ui/Badge.vue'
import Kicker from '../components/ui/Kicker.vue'
import Select from '../components/ui/Select.vue'
import Field from '../components/ui/Field.vue'
import { getAvailableModels } from '../api/simulation.js'

const { t, tm } = useI18n()
const router = useRouter()

const simulationPrompt = ref('')
const files = ref([])
const loading = ref(false)
const isDragOver = ref(false)
const fileInput = ref(null)
const errorMsg = ref('')

const ALLOWED = ['.pdf', '.md', '.txt', '.markdown']

// ---- Model + language selection (persisted) ----
const STORAGE_MODEL = 'agora.lastModel'
const STORAGE_LANG = 'agora.agentLanguage'

const ollamaModels = ref([])
const presetModels = ref([])
const defaultModel = ref('')
const ollamaReachable = ref(false)
const ollamaError = ref(null)
const neo4jReachable = ref(false)
const neo4jError = ref(null)
const loadingModels = ref(true)
const modelOption = ref(localStorage.getItem(STORAGE_MODEL) || 'default')
const customModel = ref('')
const language = ref(localStorage.getItem(STORAGE_LANG) || 'de')

async function loadStatus() {
  loadingModels.value = true
  try {
    const res = await getAvailableModels()
    if (res?.success) {
      ollamaModels.value = res.data?.ollama || []
      presetModels.value = res.data?.presets || []
      defaultModel.value = res.data?.current_default || ''
      ollamaReachable.value = !!res.data?.ollama_reachable
      ollamaError.value = res.data?.ollama_error || null
      neo4jReachable.value = !!res.data?.neo4j_reachable
      neo4jError.value = res.data?.neo4j_error || null
      if (res.data?.default_language && !localStorage.getItem(STORAGE_LANG)) {
        language.value = res.data.default_language
      }
    }
  } catch (e) {
    ollamaError.value = e.message
    neo4jError.value = e.message
  } finally {
    loadingModels.value = false
  }
}

const modelOptions = computed(() => {
  const opts = [{ value: 'default', label: `${t('step2.model.default')} — ${defaultModel.value || '?'}` }]
  for (const p of presetModels.value) {
    opts.push({ value: p.name, label: p.label || p.name })
  }
  for (const m of ollamaModels.value) {
    if (presetModels.value.some(p => p.name === m.name)) continue
    opts.push({ value: m.name, label: `${m.label || m.name} (Ollama)` })
  }
  opts.push({ value: 'custom', label: t('step2.model.customGroup') })
  return opts
})

const servicesReady = computed(() => neo4jReachable.value && (ollamaReachable.value || modelOption.value === 'custom'))

const canSubmit = computed(() => {
  return (
    simulationPrompt.value.trim() !== '' &&
    files.value.length > 0 &&
    servicesReady.value &&
    (modelOption.value !== 'custom' || customModel.value.trim() !== '')
  )
})

const triggerFileInput = () => {
  if (!loading.value) fileInput.value?.click()
}

function addFiles(newFiles) {
  const valid = newFiles.filter((f) =>
    ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext))
  )
  files.value = [...files.value, ...valid]
}

const onFileSelect = (e) => addFiles(Array.from(e.target.files))
const onDragOver = () => { isDragOver.value = true }
const onDragLeave = () => { isDragOver.value = false }
const onDrop = (e) => { isDragOver.value = false; addFiles(Array.from(e.dataTransfer.files)) }
const removeFile = (i) => { files.value.splice(i, 1) }

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function startSimulation() {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    // Persist selection so Step2 picks it up.
    localStorage.setItem(STORAGE_MODEL, modelOption.value)
    if (modelOption.value === 'custom') {
      localStorage.setItem('agora.customModel', customModel.value.trim())
    }
    localStorage.setItem(STORAGE_LANG, language.value)

    const { setPendingUpload } = await import('../store/pendingUpload.js')
    setPendingUpload(files.value, simulationPrompt.value)
    router.push({ name: 'Process', params: { projectId: 'new' } })
  } catch (err) {
    errorMsg.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStatus()
  const stored = localStorage.getItem('agora.customModel')
  if (stored) customModel.value = stored
})

function scrollToConsole() {
  document.getElementById('console')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const steps = computed(() => tm('home.steps'))
</script>

<template>
  <div class="page">
    <div class="shell">

      <!-- Top nav -->
      <header class="nav">
        <div class="brand">
          Ag<span class="n">o</span>ra
        </div>
        <nav class="nav-links">
          <a href="#console">{{ t('home.console.uploadKicker') }}</a>
          <a href="#workflow">{{ t('home.workflow.kicker') }}</a>
          <a href="#history">{{ t('history.kicker') }}</a>
        </nav>
        <div class="nav-status">
          <span class="dot"></span>
          {{ t('nav.available') }}
        </div>
      </header>

      <!-- Hero (editorial split) -->
      <section class="hero">
        <div class="hero-left">
          <div class="edition">
            <span>{{ t('home.edition') }}</span>
            <span>{{ t('home.location') }}</span>
          </div>
          <h1 class="display">
            {{ t('home.headline.line1') }}<br>
            {{ t('home.headline.line2') }}
            <span class="it">{{ t('home.headline.line3Italic') }}</span>
          </h1>
          <p class="lead">{{ t('home.lead') }}</p>
          <div class="hero-tags">
            <Badge variant="solid">{{ t('home.tags.engine') }}</Badge>
            <Badge variant="ghost">{{ t('home.tags.version') }}</Badge>
          </div>
        </div>
        <aside class="hero-right">
          <div class="portrait">
            <img src="../assets/logo/agora-logo.jpg" :alt="t('brand.name')" />
          </div>
          <div class="portrait-meta">
            <span>{{ t('brand.name').toUpperCase() }}</span>
            <span>{{ t('brand.tagline') }}</span>
          </div>
          <button class="scroll-down" @click="scrollToConsole" aria-label="↓">↓</button>
        </aside>
      </section>

      <!-- System status section -->
      <section class="section">
        <div class="section-head">
          <div class="left">
            <div class="num">02</div>
            <div class="k">{{ t('home.system.kicker') }}</div>
          </div>
          <div>
            <h2>{{ t('home.system.title') }}</h2>
            <p class="sub">{{ t('home.system.desc') }}</p>
            <div class="metrics">
              <article class="metric">
                <div class="value">{{ t('home.metrics.free.value') }}</div>
                <div class="label">{{ t('home.metrics.free.label') }}</div>
              </article>
              <article class="metric">
                <div class="value">{{ t('home.metrics.private.value') }}</div>
                <div class="label">{{ t('home.metrics.private.label') }}</div>
              </article>
              <article class="metric">
                <div class="value">{{ t('home.metrics.openSource.value') }}</div>
                <div class="label">{{ t('home.metrics.openSource.label') }}</div>
              </article>
            </div>
          </div>
        </div>
      </section>

      <!-- Workflow stepper (editorial numbered list) -->
      <section id="workflow" class="section">
        <div class="section-head">
          <div class="left">
            <div class="num">03</div>
            <div class="k">{{ t('home.workflow.kicker') }}</div>
          </div>
          <div>
            <ol class="workflow">
              <li v-for="step in steps" :key="step.num">
                <span class="step-num">{{ step.num }}</span>
                <div class="step-body">
                  <span class="step-title">{{ step.title }}</span>
                  <span class="step-desc">{{ step.desc }}</span>
                </div>
              </li>
            </ol>
          </div>
        </div>
      </section>

      <!-- Console: upload + model + prompt + start -->
      <section id="console" class="console">

        <!-- Service status strip -->
        <div class="status-strip">
          <span class="status-pill" :class="{ ok: neo4jReachable, bad: !neo4jReachable && !loadingModels }">
            <span class="status-dot" :class="neo4jReachable ? 'status-dot--done' : 'status-dot--error'" />
            Neo4j {{ loadingModels ? '…' : (neo4jReachable ? 'verbunden' : 'aus') }}
          </span>
          <span class="status-pill" :class="{ ok: ollamaReachable, bad: !ollamaReachable && !loadingModels }">
            <span class="status-dot" :class="ollamaReachable ? 'status-dot--done' : 'status-dot--error'" />
            Ollama {{ loadingModels ? '…' : (ollamaReachable ? 'verbunden' : 'aus') }}
          </span>
          <button v-if="!loadingModels" class="status-refresh" @click="loadStatus" :title="t('common.refresh')">↻</button>
        </div>
        <div v-if="!loadingModels && !servicesReady" class="status-warn">
          {{ neo4jReachable ? '' : 'Neo4j nicht erreichbar — starte: brew services start neo4j (oder docker compose up -d neo4j). ' }}
          {{ ollamaReachable ? '' : 'Ollama nicht erreichbar — starte: ollama serve.' }}
        </div>

        <div class="console-head">
          <Kicker num="04">{{ t('home.console.uploadKicker') }}</Kicker>
          <span class="console-meta">{{ t('home.console.uploadAccepted') }}</span>
        </div>

        <div
          class="dropzone"
          :class="{ 'is-dragover': isDragOver, 'has-files': files.length }"
          @dragover.prevent="onDragOver"
          @dragleave.prevent="onDragLeave"
          @drop.prevent="onDrop"
          @click="triggerFileInput"
        >
          <input
            ref="fileInput"
            type="file"
            multiple
            accept=".pdf,.md,.markdown,.txt"
            @change="onFileSelect"
            hidden
            :disabled="loading"
          />
          <div v-if="!files.length" class="dropzone-empty">
            <div class="dropzone-arrow">↑</div>
            <div class="dropzone-title">{{ t('home.console.uploadTitle') }}</div>
            <div class="dropzone-hint">{{ t('home.console.uploadHint') }}</div>
          </div>
          <ul v-else class="file-list">
            <li v-for="(f, i) in files" :key="i" class="file-row">
              <span class="file-name">{{ f.name }}</span>
              <span class="file-size">{{ formatBytes(f.size) }}</span>
              <button class="file-remove" @click.stop="removeFile(i)" aria-label="×">×</button>
            </li>
          </ul>
        </div>

        <!-- Model + language picker -->
        <div class="console-head">
          <Kicker num="05">{{ t('step2.model.label') }}</Kicker>
          <span class="console-meta">{{ t('step2.language.label') }}</span>
        </div>
        <div class="model-grid">
          <div>
            <Select
              v-model="modelOption"
              :label="t('step2.model.label')"
              :options="modelOptions"
            />
            <p v-if="!ollamaReachable && !loadingModels" class="console-warning" style="margin-top: 4px;">
              {{ t('step2.model.noOllama') }}
            </p>
          </div>
          <div>
            <Select
              v-model="language"
              :label="t('step2.language.label')"
              :options="[
                { value: 'de', label: t('step2.language.de') },
                { value: 'en', label: t('step2.language.en') },
              ]"
            />
            <p class="console-warning" style="margin-top: 4px;">
              {{ t('step2.language.hint') }}
            </p>
          </div>
        </div>
        <Field
          v-if="modelOption === 'custom'"
          v-model="customModel"
          :label="t('step2.model.customLabel')"
          :placeholder="t('step2.model.customPlaceholder')"
        />

        <!-- Prompt -->
        <div class="console-head">
          <Kicker num="06" accent>{{ t('home.console.promptKicker') }}</Kicker>
          <span class="console-meta">{{ t('home.console.engineLabel') }}</span>
        </div>

        <textarea
          v-model="simulationPrompt"
          class="prompt"
          :placeholder="t('home.console.promptPlaceholder')"
          rows="6"
          :disabled="loading"
        />

        <div class="console-actions">
          <Btn
            variant="primary"
            :disabled="!canSubmit"
            :loading="loading"
            arrow
            @click="startSimulation"
          >
            {{ loading ? t('home.console.initializing') : t('home.console.startBtn') }}
          </Btn>
          <span v-if="!files.length" class="console-warning">
            {{ t('home.console.needFiles') }}
          </span>
          <span v-else-if="!simulationPrompt.trim()" class="console-warning">
            {{ t('home.console.needPrompt') }}
          </span>
          <span v-else-if="!servicesReady" class="console-warning">
            Dienste nicht bereit (Neo4j/Ollama).
          </span>
        </div>
        <p v-if="errorMsg" class="error-line">{{ errorMsg }}</p>
      </section>

      <!-- History section -->
      <section id="history" class="section">
        <HistoryDatabase />
      </section>

    </div>

    <AppFooter />
  </div>
</template>

<style scoped>
.page {
  background: transparent; /* body provides --bg-page (radial + cream highlight) */
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* Brand */
.brand {
  font-family: var(--ff-serif);
  font-weight: 500;
  font-size: 24px;
  letter-spacing: -0.02em;
  color: var(--ink-0);
}
.brand .n { color: var(--accent); font-style: italic; }

/* Hero */
.hero {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: var(--s-7);
  padding: var(--s-9) 0 var(--s-7);
  align-items: end;
  border-bottom: 1px solid var(--ink-2);
}
.hero-left { display: flex; flex-direction: column; gap: var(--s-5); }
.edition {
  display: flex;
  justify-content: space-between;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  border-top: 1px solid var(--ink-2);
  padding-top: var(--s-3);
  margin-bottom: var(--s-5);
}
.display {
  font-family: var(--ff-serif);
  font-weight: 300;
  font-size: clamp(56px, 8vw, 132px);
  line-height: 0.98;
  letter-spacing: -0.03em;
  color: var(--ink-0);
  margin: 0;
}
.display .it {
  font-style: italic;
  font-weight: 400;
  color: var(--accent);
}
.lead {
  font-family: var(--ff-sans);
  font-size: var(--fs-18);
  line-height: 1.55;
  color: var(--fg-body);
  max-width: 56ch;
  margin: var(--s-3) 0 0;
}
.hero-tags { display: flex; gap: var(--s-3); margin-top: var(--s-5); }

.hero-right { display: flex; flex-direction: column; gap: var(--s-3); position: relative; }
.portrait {
  background: var(--paper-0);
  aspect-ratio: 1/1;
  overflow: hidden;
  border-radius: var(--r-1);
  border: 1px solid var(--rule);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--s-5);
}
.portrait img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.portrait-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-top: 1px solid var(--ink-2);
  padding-top: var(--s-3);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.portrait-meta span:last-child { text-align: right; text-transform: none; letter-spacing: 0; font-family: var(--ff-sans); color: var(--fg-body); }
.scroll-down {
  position: absolute;
  bottom: -48px;
  right: 0;
  width: 40px;
  height: 40px;
  background: transparent;
  border: 1px solid var(--ink-2);
  color: var(--accent);
  font-size: 18px;
  cursor: pointer;
  border-radius: var(--r-1);
  transition: border-color 150ms ease;
}
.scroll-down:hover { border-color: var(--accent); }

/* Section reused via global .section / .section-head */

/* System metrics */
.metrics {
  margin-top: var(--s-7);
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border-top: 1px solid var(--rule);
}
.metric {
  padding: var(--s-5) 0;
  border-right: 1px solid var(--rule);
  padding-right: var(--s-5);
}
.metric:last-child { border-right: none; }
.metric .value {
  font-family: var(--ff-serif);
  font-weight: 400;
  font-size: var(--fs-44);
  line-height: 1.05;
  color: var(--ink-0);
}
.metric .label {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-top: var(--s-2);
}

/* Workflow list */
.workflow {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}
.workflow li {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: var(--s-5);
  padding: var(--s-5) 0;
  border-top: 1px solid var(--rule);
  align-items: baseline;
}
.workflow li:last-child { border-bottom: 1px solid var(--rule); }
.step-num {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  letter-spacing: var(--ls-mono);
  color: var(--fg-muted);
}
.step-body { display: flex; flex-direction: column; gap: var(--s-2); }
.step-title {
  font-family: var(--ff-serif);
  font-weight: 400;
  font-size: var(--fs-32);
  line-height: 1.15;
  letter-spacing: -0.01em;
  color: var(--ink-0);
}
.step-desc {
  font-family: var(--ff-sans);
  font-size: var(--fs-16);
  color: var(--fg-body);
  max-width: 60ch;
}

/* Console */
.console {
  padding: var(--s-9) 0;
  border-top: 1px solid var(--ink-2);
  display: flex;
  flex-direction: column;
  gap: var(--s-5);
}
.console-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.console-meta {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.dropzone {
  border: 1px dashed var(--ink-2);
  background: var(--paper-1);
  min-height: 180px;
  cursor: pointer;
  transition: background 150ms ease, border-color 150ms ease;
  padding: var(--s-5);
}
.dropzone.is-dragover { background: var(--paper-2); border-color: var(--accent); }
.dropzone.has-files { cursor: default; padding: 0; }
.dropzone-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  height: 140px;
  text-align: center;
}
.dropzone-arrow {
  font-family: var(--ff-mono);
  font-size: 24px;
  color: var(--accent);
}
.dropzone-title {
  font-family: var(--ff-serif);
  font-size: var(--fs-24);
  color: var(--ink-0);
  font-weight: 400;
}
.dropzone-hint {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.file-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.file-row {
  display: grid;
  grid-template-columns: 1fr auto 32px;
  gap: var(--s-4);
  align-items: center;
  padding: var(--s-3) var(--s-5);
  border-bottom: 1px solid var(--paper-2);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  color: var(--ink-0);
}
.file-row:last-child { border-bottom: none; }
.file-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { color: var(--fg-muted); font-size: 11px; }
.file-remove {
  background: transparent;
  border: 0;
  color: var(--fg-muted);
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}
.file-remove:hover { color: var(--accent); }

.prompt {
  width: 100%;
  background: var(--paper-1);
  border: 1px solid var(--ink-2);
  padding: var(--s-5);
  font-family: var(--ff-mono);
  font-size: var(--fs-14);
  line-height: 1.55;
  color: var(--ink-0);
  resize: vertical;
  min-height: 160px;
  outline: none;
  border-radius: var(--r-1);
}
.prompt:focus { border-color: var(--accent); }
.prompt::placeholder { color: var(--fg-meta); }

.console-actions {
  display: flex;
  align-items: center;
  gap: var(--s-5);
}
.console-warning {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-meta);
}

.error-line {
  font-family: var(--ff-mono);
  font-size: var(--fs-12);
  color: #b00020;
  background: var(--paper-1);
  padding: var(--s-3);
  border-left: 2px solid #b00020;
  margin: 0;
  white-space: pre-wrap;
}

.status-strip {
  display: flex;
  gap: var(--s-3);
  align-items: center;
  flex-wrap: wrap;
  padding-bottom: var(--s-3);
  border-bottom: 1px solid var(--rule);
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  padding: 6px 10px;
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
}
.status-pill.ok { color: var(--ink-0); border-color: var(--ink-2); }
.status-pill.bad { color: #b00020; border-color: #b00020; }
.status-refresh {
  background: transparent;
  border: 1px solid var(--rule);
  border-radius: var(--r-pill);
  padding: 4px 10px;
  font-family: var(--ff-mono);
  font-size: 14px;
  cursor: pointer;
  color: var(--fg-muted);
}
.status-refresh:hover { color: var(--accent); border-color: var(--accent); }
.status-warn {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  color: #b00020;
  margin: 0;
}

.model-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-5) var(--s-7);
}
@media (max-width: 720px) {
  .model-grid { grid-template-columns: 1fr; }
}

/* Responsive */
@media (max-width: 880px) {
  .hero { grid-template-columns: 1fr; }
  .section-head { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: 1fr; }
  .metric { border-right: none; border-bottom: 1px solid var(--rule); }
  .nav { grid-template-columns: 1fr; }
  .nav-links { justify-self: start; }
  .scroll-down { display: none; }
}
</style>
