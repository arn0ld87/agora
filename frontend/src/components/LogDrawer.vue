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
        <div v-if="!filteredLines.length" class="meta">{{ t('logs.drawer.empty') }}</div>
        <div
          v-for="(line, i) in filteredLines"
          :key="'l' + i"
          class="log-line"
          :class="{ 'is-error': isErrorLine(line) }"
        >{{ line }}</div>
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
const scrollEl = ref(null)
const sticky = useStickyScroll(scrollEl)
// Letzter Datei-Offset aus dem Tail-Response — geben wir dem Stream als
// Wiederaufsetzpunkt mit, damit zwischen Tail und Connect geschriebene
// Lines nicht verloren gehen (PR #146-Review).
let lastOffset = null
let reconnectAttempts = 0

const RING_BUFFER_MAX = 5000
const MAX_RECONNECT_ATTEMPTS = 5
const ERROR_PATTERN = /(error|exception|traceback|fatal)/i
function isErrorLine(line) {
  return typeof line === 'string' && ERROR_PATTERN.test(line)
}

const filteredLines = computed(() => {
  if (!search.value) return lines.value
  const needle = search.value.toLowerCase()
  return lines.value.filter((ln) => typeof ln === 'string' && ln.toLowerCase().includes(needle))
})

let _eventSource = null
let _streamGeneration = 0

async function reload() {
  try {
    const res = await fetchLogs({ tail: 500, level: level.value || null })
    if (res?.data?.success) {
      const data = res.data.data || {}
      const incoming = data.lines || []
      lines.value = incoming
      const off = data.offset
      lastOffset = Number.isInteger(off) && off >= 0 ? off : null
      nextTick(() => sticky.scrollToBottom())
    }
  } catch { /* swallow */ }
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
  reconnectAttempts = 0
  streamFailed.value = false
  const generation = ++_streamGeneration
  const url = await buildLogsStreamUrl(level.value || null, lastOffset)
  if (generation !== _streamGeneration) return
  try {
    _eventSource = new EventSource(url)
    _eventSource.onmessage = (e) => {
      reconnectAttempts = 0
      if (streamFailed.value) streamFailed.value = false
      try {
        const payload = JSON.parse(e.data)
        if (payload?.line != null) appendLine(payload.line)
      } catch { /* ignore non-JSON */ }
    }
    _eventSource.onerror = (err) => {
      reconnectAttempts++
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        stopStream()
        streamFailed.value = true
        appendLine(t('logs.drawer.reconnectExhausted'), { bypassPause: true })
        return
      }
      console.warn('LogDrawer SSE error', err)
      // Connection-Diagnose muss auch bei pausiertem Auto-Scroll sichtbar
      // sein — bypassPause: true.
      appendLine(t('logs.drawer.connectionError'), { bypassPause: true })
    }
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
  background: var(--bg-elevated, #111);
  border-top: 1px solid var(--rule);
  z-index: 90;
  display: flex;
  flex-direction: column;
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.4);
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
.reconnect-btn { width: auto; padding: 0 10px; color: var(--status-error, #f56565); border-color: var(--status-error, #f56565); }
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
.log-line.is-error { color: var(--status-error, #f56565); }
.meta { color: var(--fg-muted); }
</style>
