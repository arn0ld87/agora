<template>
  <div class="log-stream">
    <header class="drawer-head">
      <span v-if="title" class="title">{{ title }}</span>
      <div class="filters">
        <select
          v-model="level"
          class="level-select"
          :aria-label="t('logs.drawer.levelFilter')"
          @change="reload"
        >
          <option value="">{{ t('logs.drawer.allLevels') }}</option>
          <option value="error">ERROR</option>
          <option value="warn">WARN</option>
          <option value="info">INFO</option>
          <option value="debug">DEBUG</option>
        </select>
        <input
          v-model="search"
          class="search-input"
          :placeholder="t('logs.drawer.search')"
          :aria-label="t('logs.drawer.search')"
          type="search"
        />
        <label class="pause-toggle">
          <input v-model="paused" type="checkbox" /> {{ t('logs.drawer.pause') }}
        </label>
        <label v-if="scopeId" class="scope-toggle">
          <input v-model="showAll" type="checkbox" class="scope-all" /> {{ t('logs.drawer.showAll') }}
        </label>
        <span
          v-if="streamReconnecting"
          class="reconnect-indicator"
          :title="t('logs.drawer.reconnecting')"
          aria-live="polite"
        >&#x21bb; {{ t('logs.drawer.reconnecting') }}</span>
        <button
          v-if="streamFailed"
          class="close-btn reconnect-btn"
          :title="t('logs.drawer.reconnect')"
          @click="manualReconnect"
        >&#x21bb; {{ t('logs.drawer.reconnect') }}</button>
        <button
          type="button"
          class="copy-btn"
          :disabled="!canCopy"
          :title="t('logs.drawer.copyTitle')"
          @click="copyVisible"
        >{{ t('logs.drawer.copy') }}</button>
        <span
          class="copy-status"
          :class="{ 'is-error': copyState === 'failed' }"
          role="status"
          aria-live="polite"
        >{{ copyState === 'copied' ? t('logs.drawer.copied') : copyState === 'failed' ? t('logs.drawer.copyFailed') : '' }}</span>
        <slot name="actions" />
      </div>
    </header>
    <p v-if="scopeActive" class="scope-note">{{ t('logs.drawer.scopeNote', { id: scopeId }) }}</p>
    <div class="drawer-body-wrap">
      <!-- tabindex="0": der Bereich scrollt und enthält selbst nichts Fokussierbares;
           ohne Fokus käme die Tastatur nicht an die älteren Zeilen (axe
           scrollable-region-focusable). -->
      <div ref="scrollEl" class="drawer-body" role="log" tabindex="0" :aria-label="t('logs.drawer.title')">
        <div v-if="loading && !lines.length" class="meta">{{ t('logs.drawer.loading') }}</div>
        <div v-else-if="errorMessage" class="meta is-error">{{ errorMessage }}</div>
        <div v-else-if="fileNotice" class="meta">{{ t(fileNotice) }}</div>
        <div v-else-if="!filteredLines.length" class="meta">{{ scopeActive ? t('logs.drawer.emptyScoped') : t('logs.drawer.empty') }}</div>
        <template v-else>
          <div
            v-for="(line, i) in filteredLines"
            :key="'l' + i"
            class="log-line"
            :class="{ 'is-error': isErrorLine(line) }"
          >{{ line }}</div>
        </template>
      </div>
      <StickyScrollBanner :count="sticky.unreadCount.value" @jump="sticky.scrollToBottom" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Protokoll-Inhalt: Stufe, Suche, Pause, Kopieren und der Livestrom von
 * `/api/logs/stream`. Konsole (`LogDrawer.vue`) und Seite `/activity/log`
 * nutzen dieselbe Komponente; wer sie aktiv schaltet, hält den Strom.
 */
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchLogs, buildLogsStreamUrl } from '../../api/logs'
import { useStickyScroll } from '../../composables/useStickyScroll'
import StickyScrollBanner from '../ui/StickyScrollBanner.vue'
import { collapseProgressLines } from '../../utils/logProgress'
import { isErrorLine } from '@/utils/errorLinePattern'
import { filterLinesByScope, parseLogFrame, parseLogTail } from '../../composables/activity/logTail'

const props = withDefaults(
  defineProps<{
    /** Strom und Tail laufen nur, solange die Komponente aktiv ist. */
    active?: boolean
    title?: string
    /** Simulationskennung des geöffneten Laufs; filtert per Textsuche. */
    scopeId?: string | null
  }>(),
  { active: true, title: '', scopeId: null },
)

const { t } = useI18n()
const lines = ref<string[]>([])
const level = ref('')
const search = ref('')
const paused = ref(false)
const showAll = ref(false)
const streamFailed = ref(false)
const streamReconnecting = ref(false)
// Loading/Error/Backend-Marker an die UI durchreichen, damit der User
// unterscheiden kann zwischen "Backend lebt, hat aber noch keine Datei für
// heute" und "Request fehlgeschlagen".
const loading = ref(false)
const errorMessage = ref<string | null>(null)
const fileNotice = ref<string | null>(null)
const scrollEl = ref<HTMLElement | null>(null)
const sticky = useStickyScroll(scrollEl)
// Letzter Datei-Offset aus dem Tail-Response — geben wir dem Stream als
// Wiederaufsetzpunkt mit, damit zwischen Tail und Connect geschriebene
// Lines nicht verloren gehen (PR #146-Review).
let lastOffset: number | null = null
let lastFrameAt = 0
let reconnectIndicatorTimer: number | null = null

const RING_BUFFER_MAX = 5000
// SSE-Reconnects sind unbegrenzt (User-Decision 2026-05-16): EventSource nutzt
// automatisches Browser-Reconnect mit dem vom Server gesetzten ``retry:``-Wert
// (5 s in stream_logs). Der ``streamReconnecting``-Indikator erscheint erst
// nach ``RECONNECT_INDICATOR_DELAY_MS`` ohne erfolgreichen Frame, damit
// kurze Hiccups (< 30 s) optisch verschluckt werden.
const RECONNECT_INDICATOR_DELAY_MS = 30000

const scopeActive = computed(() => !!props.scopeId && !showAll.value)

// Tqdm-artige Fortschrittsbalken: nur der letzte Stand je Balken.
const displayLines = computed(() => collapseProgressLines(lines.value))

const filteredLines = computed(() => {
  let out: string[] = displayLines.value
  if (scopeActive.value) out = filterLinesByScope(out, props.scopeId)
  if (!search.value) return out
  const needle = search.value.toLowerCase()
  return out.filter((ln) => typeof ln === 'string' && ln.toLowerCase().includes(needle))
})

// Kopieren: genau die sichtbaren Zeilen (nach Stufe, Lauf, Suche,
// zusammengefasste Fortschrittsbalken), eine je Eintrag, im Format der Anzeige.
const copyState = ref<'idle' | 'copied' | 'failed'>('idle')
let copyTimer: number | null = null
const canCopy = computed(() => !errorMessage.value && !fileNotice.value && filteredLines.value.length > 0)

async function copyVisible() {
  if (!canCopy.value) return
  if (copyTimer !== null) window.clearTimeout(copyTimer)
  try {
    await navigator.clipboard.writeText(filteredLines.value.join('\n'))
    copyState.value = 'copied'
    copyTimer = window.setTimeout(() => { copyState.value = 'idle'; copyTimer = null }, 2000)
  } catch {
    // Fehler bleibt sichtbar, bis erneut kopiert wird.
    copyState.value = 'failed'
    copyTimer = null
  }
}

let eventSource: EventSource | null = null
let streamGeneration = 0

async function reload() {
  loading.value = true
  errorMessage.value = null
  fileNotice.value = null
  try {
    const res: unknown = await fetchLogs({ tail: 500, level: level.value || null })
    const parsed = parseLogTail(res)
    if (parsed.ok) {
      lines.value = parsed.data.lines
      const off = parsed.data.offset
      lastOffset = Number.isInteger(off) && off !== undefined && off >= 0 ? off : null
      // Backend-Marker bei file=null durchreichen (z. B. heutige Logdatei
      // noch nicht angelegt) — User sieht so, dass das Backend lebt.
      if (parsed.data.file === null && parsed.data.message) {
        fileNotice.value = parsed.data.message
      }
      nextTick(() => sticky.scrollToBottom())
    } else {
      errorMessage.value = parsed.error || t('logs.drawer.unknownError')
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function appendLine(line: string) {
  if (paused.value) return
  lines.value.push(line)
  if (lines.value.length > RING_BUFFER_MAX) {
    lines.value.splice(0, lines.value.length - RING_BUFFER_MAX)
  }
  nextTick(() => sticky.markAppended(1))
}

async function startStream() {
  stopStream()
  streamFailed.value = false
  streamReconnecting.value = false
  lastFrameAt = Date.now()
  const generation = ++streamGeneration
  const url = await buildLogsStreamUrl(level.value || null, lastOffset)
  if (generation !== streamGeneration) return
  try {
    eventSource = new EventSource(url)
    eventSource.onmessage = (e: MessageEvent) => {
      lastFrameAt = Date.now()
      streamReconnecting.value = false
      const line = parseLogFrame(e.data)
      if (line !== null) appendLine(line)
    }
    eventSource.onerror = () => {
      // EventSource macht automatisches Reconnect mit dem vom Server gesetzten
      // ``retry:``-Wert. Kein Spam in die Zeilen — der Indikator reicht, wenn
      // der Drift > RECONNECT_INDICATOR_DELAY_MS ist.
      if (Date.now() - lastFrameAt > RECONNECT_INDICATOR_DELAY_MS) {
        streamReconnecting.value = true
      }
    }
    reconnectIndicatorTimer = window.setInterval(() => {
      if (Date.now() - lastFrameAt > RECONNECT_INDICATOR_DELAY_MS) {
        streamReconnecting.value = true
      }
    }, 5000)
  } catch { /* ignore */ }
}

function manualReconnect() {
  void startStream()
}

function stopStream() {
  // Ein noch ausstehender Verbindungsaufbau (Ticket wird geholt) darf nach dem
  // Stopp keine Verbindung mehr öffnen.
  streamGeneration++
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  if (reconnectIndicatorTimer !== null) {
    window.clearInterval(reconnectIndicatorTimer)
    reconnectIndicatorTimer = null
  }
  streamReconnecting.value = false
}

watch(() => props.active, async (isActive) => {
  if (isActive) {
    await reload()
    void startStream()
  } else {
    stopStream()
  }
})

watch(level, () => {
  if (props.active) {
    void reload()
    void startStream()
  }
})

onMounted(() => { if (props.active) { void reload(); void startStream() } })
onUnmounted(() => {
  stopStream()
  if (copyTimer !== null) window.clearTimeout(copyTimer)
})
</script>

<style scoped>
.log-stream {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  font-family: var(--ag-font-sans);
}
.reconnect-indicator {
  font-size: 12px;
  color: var(--fg3);
  padding: 2px 8px;
  border-radius: var(--ag-r-6);
  background: var(--s3);
  animation: reconnect-pulse 1.6s ease-in-out infinite;
}
@keyframes reconnect-pulse {
  0%, 100% { opacity: 0.5; }
  50%      { opacity: 1; }
}
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  font-size: 13px;
  color: var(--fg3);
}
.drawer-head .title { color: var(--fg); font-weight: 600; font-size: 14px; }
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.level-select, .search-input {
  background: var(--field);
  border: none;
  color: var(--fg);
  height: 32px;
  padding: 0 10px;
  font: inherit;
  font-size: 13px;
  border-radius: var(--ag-r-8);
}
.search-input { min-width: 180px; }
.level-select:focus-visible, .search-input:focus-visible,
.close-btn:focus-visible { outline: 2px solid var(--acc); outline-offset: 1px; }
.pause-toggle, .scope-toggle { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
.scope-note { margin: 0; padding: 0 16px 6px; font-size: 12px; color: var(--fg3); }
.close-btn {
  background: transparent;
  border: none;
  color: var(--fg2);
  width: 32px; height: 32px;
  border-radius: var(--ag-r-8);
  cursor: pointer;
  font: inherit;
}
.close-btn:hover { background: var(--s3); color: var(--fg); }
.copy-btn {
  background: transparent;
  border: none;
  color: var(--fg2);
  height: 32px;
  padding: 0 10px;
  border-radius: var(--ag-r-8);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}
.copy-btn:hover:not(:disabled) { background: var(--s3); color: var(--fg); }
.copy-btn:focus-visible { outline: 2px solid var(--acc); outline-offset: 1px; }
.copy-btn:disabled { opacity: 0.5; cursor: default; }
.copy-status { font-size: 12px; color: var(--fg3); }
.copy-status.is-error { color: var(--err); }
.reconnect-btn { width: auto; padding: 0 10px; color: var(--err); background: var(--err-soft); }
.reconnect-btn:hover { background: var(--err-soft); color: var(--fg); }

.drawer-body-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.drawer-body {
  height: 100%;
  overflow-y: auto;
  font-family: var(--ag-font-mono);
  font-size: 12px;
  line-height: 1.5;
  padding: 4px 16px 12px;
  color: var(--fg);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.drawer-body:focus-visible { outline: 2px solid var(--acc-text); outline-offset: -2px; }
.log-line { padding: 3px 0; border-top: 1px solid var(--line); }
.log-line:first-child { border-top: none; }
.log-line.is-error { color: var(--err); }
.meta { color: var(--fg3); font-family: var(--ag-font-sans); font-size: 13px; padding: 12px 0; }
.meta.is-error { color: var(--err); }
</style>
