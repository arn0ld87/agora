<template>
  <div v-if="open" class="log-drawer" role="region" :aria-label="t('logs.drawer.title')">
    <header class="drawer-head">
      <span class="title">{{ t('logs.drawer.title') }}</span>
      <div class="filters">
        <select v-model="level" class="level-select" @change="reload">
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
          type="search"
        />
        <label class="pause-toggle">
          <input type="checkbox" v-model="paused" /> {{ t('logs.drawer.pause') }}
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
          @click="manualReconnect"
          :title="t('logs.drawer.reconnect')"
        >&#x21bb; {{ t('logs.drawer.reconnect') }}</button>
        <button class="close-btn" @click="$emit('close')" :title="t('common.close')">✕</button>
      </div>
    </header>
    <div class="drawer-body-wrap">
      <div ref="scrollEl" class="drawer-body">
        <div v-if="loading && !lines.length" class="meta">{{ t('logs.drawer.loading') }}</div>
        <div v-else-if="errorMessage" class="meta is-error">{{ errorMessage }}</div>
        <div v-else-if="fileNotice" class="meta">{{ t(fileNotice) }}</div>
        <div v-else-if="!filteredLines.length" class="meta">{{ t('logs.drawer.empty') }}</div>
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

<script setup>
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { fetchLogs, buildLogsStreamUrl } from '../api/logs'
import { useStickyScroll } from '../composables/useStickyScroll'
import StickyScrollBanner from './ui/StickyScrollBanner.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
})
defineEmits(['close'])

const { t } = useI18n()
const lines = ref([])
const level = ref('')
const search = ref('')
const paused = ref(false)
const streamFailed = ref(false)
const streamReconnecting = ref(false)
// Task 7 — Loading/Error/Backend-Marker an die UI durchreichen, damit der
// User unterscheiden kann zwischen "Backend lebt, hat aber noch keine
// Datei für heute" und "Request fehlgeschlagen".
const loading = ref(false)
const errorMessage = ref(null)
const fileNotice = ref(null)
const scrollEl = ref(null)
const sticky = useStickyScroll(scrollEl)
// Letzter Datei-Offset aus dem Tail-Response — geben wir dem Stream als
// Wiederaufsetzpunkt mit, damit zwischen Tail und Connect geschriebene
// Lines nicht verloren gehen (PR #146-Review).
let lastOffset = null
let lastFrameAt = 0
let _reconnectIndicatorTimer = null

const RING_BUFFER_MAX = 5000
// SSE-Reconnects sind unbegrenzt (User-Decision 2026-05-16): EventSource nutzt
// automatisches Browser-Reconnect mit dem vom Server gesetzten ``retry:``-Wert
// (5 s in stream_logs). Der ``streamReconnecting``-Indikator erscheint erst
// nach ``RECONNECT_INDICATOR_DELAY_MS`` ohne erfolgreichen Frame, damit
// kurze Hiccups (< 30 s) optisch verschluckt werden.
const RECONNECT_INDICATOR_DELAY_MS = 30000
import { isErrorLine } from '@/utils/errorLinePattern'

const filteredLines = computed(() => {
  if (!search.value) return lines.value
  const needle = search.value.toLowerCase()
  return lines.value.filter((ln) => typeof ln === 'string' && ln.toLowerCase().includes(needle))
})

let _eventSource = null
let _streamGeneration = 0

async function reload() {
  loading.value = true
  errorMessage.value = null
  fileNotice.value = null
  try {
    const res = await fetchLogs({ tail: 500, level: level.value || null })
    if (res?.data?.success) {
      const data = res.data.data || {}
      const incoming = data.lines || []
      lines.value = incoming
      const off = data.offset
      lastOffset = Number.isInteger(off) && off >= 0 ? off : null
      // Backend-Marker bei file=null durchreichen (z. B. heutige Logdatei
      // noch nicht angelegt) — User sieht so, dass das Backend lebt.
      if (data.file === null && data.message) {
        fileNotice.value = data.message
      }
      nextTick(() => sticky.scrollToBottom())
    } else {
      errorMessage.value = res?.data?.error || t('logs.drawer.unknownError')
    }
  } catch (err) {
    errorMessage.value = err?.message || String(err)
  } finally {
    loading.value = false
  }
}

function appendLine(line, { bypassPause = false } = {}) {
  // bypassPause=true: Connection-Diagnostik o. ä., die auch bei pausiertem
  // Auto-Scroll sichtbar bleiben muss. (Sub-Slice J.5 Followup, PR #232.)
  if (paused.value && !bypassPause) return
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
  const generation = ++_streamGeneration
  const url = await buildLogsStreamUrl(level.value || null, lastOffset)
  if (generation !== _streamGeneration) return
  try {
    _eventSource = new EventSource(url)
    _eventSource.onmessage = (e) => {
      lastFrameAt = Date.now()
      streamReconnecting.value = false
      try {
        const payload = JSON.parse(e.data)
        if (payload?.line != null) appendLine(payload.line)
      } catch { /* ignore non-JSON */ }
    }
    _eventSource.onerror = (err) => {
      // EventSource macht automatisches Reconnect mit dem vom Server gesetzten
      // ``retry:``-Wert. Wir spammen die Drawer-Lines NICHT mehr mit
      // "Verbindung unterbrochen"-Meldungen — Indikator-Banner reicht, wenn
      // der Drift > RECONNECT_INDICATOR_DELAY_MS ist.
      console.warn('LogDrawer SSE error', err)
      if (Date.now() - lastFrameAt > RECONNECT_INDICATOR_DELAY_MS) {
        streamReconnecting.value = true
      }
    }
    _reconnectIndicatorTimer = window.setInterval(() => {
      if (Date.now() - lastFrameAt > RECONNECT_INDICATOR_DELAY_MS) {
        streamReconnecting.value = true
      }
    }, 5000)
  } catch { /* ignore */ }
}

function manualReconnect() {
  startStream()
}

function stopStream() {
  if (_eventSource) {
    _eventSource.close()
    _eventSource = null
  }
  if (_reconnectIndicatorTimer !== null) {
    window.clearInterval(_reconnectIndicatorTimer)
    _reconnectIndicatorTimer = null
  }
  streamReconnecting.value = false
}

watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    await reload()
    startStream()
  } else {
    stopStream()
  }
})

watch(level, () => {
  if (props.open) {
    reload()
    startStream()
  }
})

onMounted(() => { if (props.open) { reload(); startStream() } })
onUnmounted(stopStream)
</script>

<style scoped>
.log-drawer {
  position: fixed;
  bottom: 0; left: 0; right: 0;
  height: min(50vh, 480px);
  background: var(--bg-elevated);
  border-top: 1px solid var(--rule);
  z-index: 90;
  display: flex;
  flex-direction: column;
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.4);
}
.reconnect-indicator {
  font-family: var(--ff-mono);
  font-size: 10px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  padding: 2px 8px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  opacity: 0.7;
  animation: reconnect-pulse 1.6s ease-in-out infinite;
}
@keyframes reconnect-pulse {
  0%, 100% { opacity: 0.4; }
  50%      { opacity: 0.9; }
}
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--s-3) var(--s-4);
  border-bottom: 1px solid var(--rule);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}
.drawer-head .title { color: var(--fg); }
.filters { display: flex; gap: var(--s-3); align-items: center; }
.level-select, .search-input {
  background: var(--bg);
  border: 1px solid var(--rule);
  color: var(--fg);
  padding: 4px 8px;
  font-family: var(--ff-mono);
  font-size: 11px;
  border-radius: var(--r-1);
}
.search-input { min-width: 180px; }
.pause-toggle { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
.close-btn {
  background: transparent;
  border: 1px solid var(--rule);
  color: var(--fg-muted);
  width: 28px; height: 28px;
  border-radius: var(--r-1);
  cursor: pointer;
}
.close-btn:hover { color: var(--fg); border-color: var(--accent); }
.reconnect-btn { width: auto; padding: 0 10px; color: var(--status-error); border-color: var(--status-error); }
.reconnect-btn:hover { color: var(--fg); border-color: var(--accent); }

.drawer-body-wrap {
  position: relative;
  flex: 1;
  overflow: hidden;
}
.drawer-body {
  height: 100%;
  overflow-y: auto;
  font-family: var(--ff-mono);
  font-size: 12px;
  line-height: 1.5;
  padding: var(--s-3) var(--s-4);
  color: var(--mono-100);
  white-space: pre-wrap;
  word-wrap: break-word;
}
.log-line { padding: 1px 0; }
.log-line.is-error { color: var(--status-error); }
.meta { color: var(--fg-muted); }
</style>
