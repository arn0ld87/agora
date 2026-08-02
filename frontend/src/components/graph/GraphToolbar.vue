<template>
  <div class="panel-header">
    <span class="panel-title">{{ $t('graph.panel') }}</span>
    <div class="header-tools">
      <button
        class="tool-btn"
        :disabled="loading"
        :title="$t('common.refresh')"
        @click="$emit('refresh')"
      >
        <span class="icon-refresh" :class="{ spinning: loading }">↻</span>
        <span class="btn-text">{{ $t('common.refresh') }}</span>
      </button>
      <button
        v-if="hasGraphData"
        class="tool-btn"
        :title="isPaused ? $t('graph.ui.resumeLayout') : $t('graph.ui.pauseLayout')"
        :aria-pressed="isPaused"
        @click="$emit('toggle-pause')"
      >
        <span class="icon-pause">{{ isPaused ? '▶' : '⏸' }}</span>
        <span class="btn-text">{{ isPaused ? $t('graph.ui.resumeLayout') : $t('graph.ui.pauseLayout') }}</span>
      </button>
      <button
        v-if="hasGraphData"
        class="tool-btn"
        :title="$t('graph.ui.resetLayout')"
        @click="$emit('reset-layout')"
      >
        <span class="icon-reset">⟲</span>
        <span class="btn-text">{{ $t('graph.ui.resetLayout') }}</span>
      </button>
      <button
        v-if="hasGraphId"
        class="tool-btn"
        title="Export as GraphML"
        @click="$emit('download-graphml')"
      >
        <span class="btn-text">.graphml</span>
      </button>
      <button
        v-if="hasGraphData"
        class="tool-btn"
        title="Export current view as SVG"
        @click="$emit('download-svg')"
      >
        <span class="btn-text">.svg</span>
      </button>
      <button
        v-if="hasGraphData"
        class="tool-btn"
        title="Export current view as PNG"
        @click="$emit('download-png')"
      >
        <span class="btn-text">.png</span>
      </button>
      <button
        v-if="hasGraphData"
        class="tool-btn"
        title="Print / save current view as PDF"
        @click="$emit('print-pdf')"
      >
        <span class="btn-text">.pdf</span>
      </button>
      <button
        v-if="hasGraphData"
        class="tool-btn"
        :title="$t('graph.ui.exportHtml')"
        @click="$emit('download-html')"
      >
        <span class="btn-text">.html</span>
      </button>
      <button
        class="tool-btn"
        :title="isMaximized ? $t('graph.ui.restoreLayout') : $t('graph.ui.maximizeLayout')"
        :aria-pressed="isMaximized"
        @click="$emit('toggle-maximize')"
      >
        <span class="icon-maximize">⛶</span>
      </button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  loading: { type: Boolean, default: false },
  hasGraphId: { type: Boolean, default: false },
  hasGraphData: { type: Boolean, default: false },
  isPaused: { type: Boolean, default: false },
  // Issue #1023 (Befund B-08): der Maximize-Button emittierte toggle-maximize
  // ins Leere (kein Listener an der einzigen Konsument-Stelle
  // StepGraphBuildView.vue). Jetzt verdrahtet auf einen CSS-Vollbild-Toggle
  // (kein requestFullscreen im Repo — bewusst kein Browser-Fullscreen).
  isMaximized: { type: Boolean, default: false },
})

defineEmits([
  'refresh',
  'download-graphml',
  'download-svg',
  'download-png',
  'print-pdf',
  'download-html',
  'toggle-maximize',
  'toggle-pause',
  'reset-layout',
])
</script>

<style scoped>
.panel-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: var(--s-4) var(--s-5);
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(to bottom, var(--bg), transparent);
  pointer-events: none;
}

.panel-title {
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  font-weight: 500;
  color: var(--fg-muted);
  pointer-events: auto;
}

.header-tools {
  pointer-events: auto;
  display: flex;
  gap: var(--s-2);
  align-items: center;
}

.tool-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--rule);
  background: var(--bg);
  border-radius: var(--r-1);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  color: var(--fg-muted);
  transition: border-color 150ms ease, color 150ms ease;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}

.tool-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.tool-btn .btn-text {
  font-size: 11px;
}

.icon-refresh.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Design v3 toolbar. */
.tool-btn {
  background: var(--surface-elevated, var(--bg));
  border-color: var(--hairline, var(--rule));
  border-radius: var(--r-5, var(--r-1));
  color: var(--text-secondary, var(--fg-muted));
  font-family: var(--font-sans, var(--ff-sans));
  letter-spacing: 0;
  text-transform: none;
  box-shadow: var(--shadow-control, none);
}
.tool-btn:hover {
  background: var(--surface-hover, transparent);
}
</style>
