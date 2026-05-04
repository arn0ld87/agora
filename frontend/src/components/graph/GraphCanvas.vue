<template>
  <div class="graph-container" ref="graphContainer">
    <!-- Graph Visualization -->
    <div v-if="graphData" class="graph-view">
      <svg ref="graphSvg" class="graph-svg"></svg>

      <GraphHints
        :current-phase="currentPhase"
        :is-simulating="isSimulating"
        :show-finished-hint="showFinishedHint"
        @dismiss-finished="$emit('dismiss-finished-hint')"
      />

      <GraphDetailPanel
        v-if="selectedItem"
        :item="selectedItem"
        :expanded-self-loops="expandedSelfLoops"
        @close="closeDetailPanel"
        @toggle-self-loop="toggleSelfLoop"
      />
    </div>

    <!-- Loading State -->
    <div v-else-if="loading" class="graph-state">
      <div class="loading-spinner"></div>
      <p>Loading graph data...</p>
    </div>

    <!-- Waiting/Empty State -->
    <div v-else class="graph-state">
      <div class="empty-icon">❖</div>
      <p class="empty-text">Waiting for ontology generation...</p>
    </div>

    <!-- Show Edge Labels Toggle -->
    <div v-if="graphData" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">{{ t('graph.ui.toggleEdgeLabels') }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, toRef, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import GraphDetailPanel from './GraphDetailPanel.vue'
import GraphHints from './GraphHints.vue'
import { useGraphRender } from '../../composables/useGraphRender'
import { exportGraphMl } from '../../api/graph'

const { t, locale } = useI18n()

const props = defineProps({
  graphData: { type: Object, default: null },
  entityTypes: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  currentPhase: { type: Number, default: null },
  isSimulating: { type: Boolean, default: false },
  showFinishedHint: { type: Boolean, default: false },
  // Issue #137 SUB2 — forwarded from MainView → GraphPanel → here.
  // Passed into useGraphRender so Auto-Freeze fires per committed batch.
  // Shape: { batch_count, total_batches, batch_at } | null
  batchSignal: { type: Object, default: null },
})

defineEmits(['dismiss-finished-hint'])

const graphContainer = ref(null)
const graphSvg = ref(null)
const showEdgeLabels = ref(true)
const expandedSelfLoops = ref(new Set())

// D3-Renderlogik (Issue #35) — Lifecycle/Resize/Watch im Composable;
// `selectedItem` wird vom Composable gehalten und hier nur gelesen + zurückgesetzt.
// `translateLabel` reicht den vue-i18n-Hook in das Composable: Edge-Labels werden
// gemäß aktueller Locale formatiert (Issue #129).
// Issue #137 SUB2: batchSignal triggers Auto-Freeze per committed chunk.
// The prop is typed as Object (plain JS script), but useGraphRender accepts
// MaybeRefOrGetter<BuildProgressDetail | null> — the shape is compatible.
const batchSignalRef = computed(() => props.batchSignal ?? null)
const { selectedItem, render, isPaused, togglePause } = useGraphRender({
  svgRef: graphSvg,
  containerRef: graphContainer,
  graphData: toRef(props, 'graphData'),
  entityTypes: toRef(props, 'entityTypes'),
  showEdgeLabels,
  translateLabel: t,
  batchSignal: batchSignalRef,
})

// Locale-Wechsel: Edge-Labels frisch durch i18n laufen lassen.
watch(locale, () => {
  render()
})

const toggleSelfLoop = (id) => {
  const newSet = new Set(expandedSelfLoops.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  expandedSelfLoops.value = newSet
}

const closeDetailPanel = () => {
  selectedItem.value = null
  expandedSelfLoops.value = new Set()
}

function _triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 500)
}

async function downloadGraphml() {
  const gid = props.graphData?.graph_id
  if (!gid) return
  try {
    const res = await exportGraphMl(gid)
    const blob = res?.data instanceof Blob
      ? res.data
      : new Blob([res?.data ?? ''], { type: 'application/xml' })
    _triggerBlobDownload(blob, `agora-graph-${gid}.graphml`)
  } catch (e) {
    console.error('GraphML export failed', e)
  }
}

// Slice 5.4 — collect every --token from :root so the cloned, off-document
// SVG can resolve var(--rule-strong) etc. without our scoped Vue classes.
function _collectRootCssVariables() {
  const root = document.documentElement
  const styles = getComputedStyle(root)
  const decls = []
  for (let i = 0; i < styles.length; i++) {
    const name = styles.item(i)
    if (name.startsWith('--')) {
      decls.push(`${name}: ${styles.getPropertyValue(name).trim()};`)
    }
  }
  return `:root {\n${decls.join('\n')}\n}`
}

function _buildStandaloneSvg() {
  const live = graphSvg.value
  if (!live) return null
  const clone = live.cloneNode(true)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink')

  const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  styleEl.textContent = `${_collectRootCssVariables()}\nsvg { background: var(--bg-canvas, #fff); }\ntext { font-family: var(--font-sans, sans-serif); }`
  clone.insertBefore(styleEl, clone.firstChild)

  const serializer = new XMLSerializer()
  const body = '<?xml version="1.0" encoding="UTF-8"?>\n' + serializer.serializeToString(clone)
  return {
    body,
    width: parseInt(live.getAttribute('width') || '0', 10) || live.clientWidth,
    height: parseInt(live.getAttribute('height') || '0', 10) || live.clientHeight,
  }
}

function downloadSvg() {
  const out = _buildStandaloneSvg()
  if (!out) return
  const gid = props.graphData?.graph_id || 'graph'
  _triggerBlobDownload(
    new Blob([out.body], { type: 'image/svg+xml;charset=utf-8' }),
    `agora-graph-${gid}.svg`,
  )
}

async function downloadPng() {
  const out = _buildStandaloneSvg()
  if (!out) return
  const gid = props.graphData?.graph_id || 'graph'
  const { width, height } = out
  if (!width || !height) {
    console.warn('PNG export: SVG has zero dimensions')
    return
  }

  const blob = await new Promise((resolve, reject) => {
    const img = new Image()
    const svgBlob = new Blob([out.body], { type: 'image/svg+xml;charset=utf-8' })
    const svgUrl = URL.createObjectURL(svgBlob)
    img.onload = () => {
      try {
        const scale = window.devicePixelRatio > 1 ? 2 : 1
        const canvas = document.createElement('canvas')
        canvas.width = width * scale
        canvas.height = height * scale
        const ctx = canvas.getContext('2d')
        ctx.scale(scale, scale)
        ctx.drawImage(img, 0, 0, width, height)
        canvas.toBlob((b) => {
          URL.revokeObjectURL(svgUrl)
          if (b) resolve(b)
          else reject(new Error('canvas.toBlob returned null'))
        }, 'image/png')
      } catch (err) {
        URL.revokeObjectURL(svgUrl)
        reject(err)
      }
    }
    img.onerror = (err) => {
      URL.revokeObjectURL(svgUrl)
      reject(err)
    }
    img.src = svgUrl
  }).catch((e) => {
    console.error('PNG export failed', e)
    return null
  })

  if (blob) {
    _triggerBlobDownload(blob, `agora-graph-${gid}.png`)
  }
}

// Slice 5.5 — PDF for the graph piggybacks on the browser print dialog.
// No jsPDF / weasyprint dependency: open a fresh window pointing at a
// Blob URL with the standalone SVG, trigger print, let the user pick
// "Save as PDF".
function printPdf() {
  const out = _buildStandaloneSvg()
  if (!out) return
  const gid = props.graphData?.graph_id || 'graph'
  const html = `<!doctype html>
<html lang="de"><head><meta charset="utf-8" />
<title>Agora-Graph · ${gid}</title>
<style>
  html, body { margin: 0; padding: 0; background: #fff; }
  body { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  svg { max-width: 100%; max-height: 100vh; }
  @media print { body { min-height: auto; } }
</style>
</head><body>
${out.body}
</body></html>`
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const w = window.open(url, '_blank')
  if (!w) {
    URL.revokeObjectURL(url)
    console.warn('Popup blocked — cannot open print window for graph PDF')
    return
  }
  const cleanup = () => {
    setTimeout(() => URL.revokeObjectURL(url), 30000)
  }
  w.addEventListener('load', () => {
    setTimeout(() => {
      try { w.print() } finally { cleanup() }
    }, 200)
  })
}

defineExpose({
  downloadGraphml,
  downloadSvg,
  downloadPng,
  printPdf,
  isPaused,
  togglePause,
})
</script>

<style scoped>
.graph-container {
  width: 100%;
  height: 100%;
}

.graph-view, .graph-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.graph-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: var(--fg-muted);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.3;
  color: var(--fg-muted);
}

.loading-spinner {
  width: 32px;
  height: 32px;
  border: 1.5px solid var(--rule);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto var(--s-3);
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Edge Labels Toggle - Top Right */
.edge-labels-toggle {
  position: absolute;
  top: 60px;
  right: var(--s-5);
  display: flex;
  align-items: center;
  gap: var(--s-2);
  background: var(--bg);
  padding: 6px 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--rule);
  z-index: 10;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--rule-strong);
  border-radius: 22px;
  transition: 0.3s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: var(--mono-50);
  border-radius: 50%;
  transition: 0.3s;
}

input:checked + .slider {
  background-color: var(--plasma-400);
}

input:checked + .slider:before {
  transform: translateX(18px);
}

.toggle-label {
  font-size: 12px;
  color: var(--fg-meta);
}
</style>
