<template>
  <div class="graph-panel">
    <div class="panel-header">
      <span class="panel-title">{{ $t('graph.panel') }}</span>
      <!-- Top Toolbar (Internal Top Right) -->
      <div class="header-tools">
        <button class="tool-btn" @click="$emit('refresh')" :disabled="loading" :title="$t('common.refresh')">
          <span class="icon-refresh" :class="{ 'spinning': loading }">↻</span>
          <span class="btn-text">{{ $t('common.refresh') }}</span>
        </button>
        <button
          v-if="graphData?.graph_id"
          class="tool-btn"
          @click="downloadGraphml"
          title="Export as GraphML"
        >
          <span class="btn-text">.graphml</span>
        </button>
        <button
          v-if="graphData"
          class="tool-btn"
          @click="downloadSvg"
          title="Export current view as SVG"
        >
          <span class="btn-text">.svg</span>
        </button>
        <button
          v-if="graphData"
          class="tool-btn"
          @click="downloadPng"
          title="Export current view as PNG"
        >
          <span class="btn-text">.png</span>
        </button>
        <button
          v-if="graphData"
          class="tool-btn"
          @click="printGraphPdf"
          title="Print / save current view as PDF"
        >
          <span class="btn-text">.pdf</span>
        </button>
        <button class="tool-btn" @click="$emit('toggle-maximize')" title="Maximize/Restore">
          <span class="icon-maximize">⛶</span>
        </button>
      </div>
    </div>
    
    <div class="graph-container" ref="graphContainer">
      <!-- Graph Visualization -->
      <div v-if="graphData" class="graph-view">
        <svg ref="graphSvg" class="graph-svg"></svg>
        
        <!-- Building/Simulating Hint -->
        <div v-if="currentPhase === 1 || isSimulating" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
              <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-4.04z" />
            </svg>
          </div>
          {{ isSimulating ? 'GraphRAG short-term/long-term memory updating in real-time' : 'Updating in real-time...' }}
        </div>
        
        <!-- Simulation Finished Hint -->
        <div v-if="showSimulationFinishedHint" class="graph-building-hint finished-hint">
          <div class="hint-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="hint-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <span class="hint-text">Some content is still being processed. It is recommended to manually refresh the graph later</span>
          <button class="hint-close-btn" @click="dismissFinishedHint" title="Close hint">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
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
    </div>

    <GraphLegend v-if="graphData && entityTypes.length" :entity-types="entityTypes" />

    <!-- Issue #10 — Temporal-Round-Slider (only visible once the graph carries simulation rounds) -->
    <GraphRoundSlider
      v-if="graphData && maxRound > 0"
      v-model="selectedRound"
      :max-round="maxRound"
    />
    
    <!-- Show Edge Labels Toggle -->
    <div v-if="graphData" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">Show Edge Labels</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'

import GraphDetailPanel from './graph/GraphDetailPanel.vue'
import GraphLegend from './graph/GraphLegend.vue'
import GraphRoundSlider from './graph/GraphRoundSlider.vue'
import {
  buildGraphRenderData,
  filterEdgesAtRound,
  getMaxRoundFromEdges,
} from './graph/graphPanelData'
import { getLinkMidpoint, getLinkPath } from './graph/graphPanelGeometry'
import { buildEntityTypes } from './graph/graphPanelUtils'
import { exportGraphMl } from '../api/graph'

const props = defineProps({
  graphData: Object,
  loading: Boolean,
  currentPhase: Number,
  isSimulating: Boolean
})

defineEmits(['refresh', 'toggle-maximize'])

const graphContainer = ref(null)
const graphSvg = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(true) // Default show edge labels
const expandedSelfLoops = ref(new Set()) // Expanded self-loop items
const showSimulationFinishedHint = ref(false) // Simulation finished hint
const wasSimulating = ref(false) // Track whether was simulating before
// Issue #10 — Temporal-Slider state. null means "live" (= maxRound, all current edges).
const selectedRound = ref(null)

const maxRound = computed(() => getMaxRoundFromEdges(props.graphData?.edges))

const displayedGraphData = computed(() => {
  if (!props.graphData) return null
  if (selectedRound.value == null) return props.graphData
  return {
    ...props.graphData,
    edges: filterEdgesAtRound(props.graphData.edges, selectedRound.value),
  }
})

// Dismiss simulation finished hint
const dismissFinishedHint = () => {
  showSimulationFinishedHint.value = false
}

// Watch isSimulating change, detect simulation end
watch(() => props.isSimulating, (newValue) => {
  if (wasSimulating.value && !newValue) {
    // Changed from simulating to not simulating, show finished hint
    showSimulationFinishedHint.value = true
  }
  wasSimulating.value = newValue
}, { immediate: true })

// Toggle self-loop item expand/collapse state
const toggleSelfLoop = (id) => {
  const newSet = new Set(expandedSelfLoops.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  expandedSelfLoops.value = newSet
}

const entityTypes = computed(() => buildEntityTypes(props.graphData))

const closeDetailPanel = () => {
  selectedItem.value = null
  expandedSelfLoops.value = new Set() // Reset expand state
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
function printGraphPdf() {
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

let currentSimulation = null
let linkLabelsRef = null
let linkLabelBgRef = null

const renderGraph = () => {
  if (!graphSvg.value || !displayedGraphData.value) return

  // Stop previous simulation
  if (currentSimulation) {
    currentSimulation.stop()
  }

  const container = graphContainer.value
  const width = container.clientWidth
  const height = container.clientHeight

  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)

  svg.selectAll('*').remove()

  const { nodes, edges, getColor } = buildGraphRenderData(displayedGraphData.value, entityTypes.value)
  if (nodes.length === 0) return

  // Simulation - dynamically adjust node spacing based on edge count
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
      // Dynamically adjust distance based on edge count between this pair of nodes
      // Base distance 150, add 40 for each additional edge
      const baseDistance = 150
      const edgeCount = d.pairTotal || 1
      return baseDistance + (edgeCount - 1) * 50
    }))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(50))
    // Add center gravity to cluster independent node groups to center area
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))
  
  currentSimulation = simulation

  const g = svg.append('g')
  
  // Zoom
  svg.call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  }))

  // Links - use path to support curves
  const linkGroup = g.append('g').attr('class', 'links')

  const link = linkGroup.selectAll('path')
    .data(edges)
    .enter().append('path')
    .attr('stroke', 'var(--rule-strong)')
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      // Reset previous selected edge style
      linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'var(--bg-inverse)')
      linkLabels.attr('fill', 'var(--fg-meta)')
      // Highlight currently selected edge
      d3.select(event.target).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)

      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels background (white background for clearer text)
  const linkLabelBg = linkGroup.selectAll('rect')
    .data(edges)
    .enter().append('rect')
    .attr('fill', 'var(--bg-inverse)')
    .attr('rx', 3)
    .attr('ry', 3)
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'var(--bg-inverse)')
      linkLabels.attr('fill', 'var(--fg-meta)')
      // Highlight corresponding edge
      link.filter(l => l === d).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)
      d3.select(event.target).attr('fill', 'var(--plasma-soft)')

      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels
  const linkLabels = linkGroup.selectAll('text')
    .data(edges)
    .enter().append('text')
    .text(d => d.name)
    .attr('font-size', '9px')
    .attr('fill', 'var(--fg-meta)')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('font-family', 'system-ui, sans-serif')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'var(--bg-inverse)')
      linkLabels.attr('fill', 'var(--fg-meta)')
      // Highlight corresponding edge
      link.filter(l => l === d).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)
      d3.select(event.target).attr('fill', 'var(--plasma-400)')

      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Save references for external control of visibility
  linkLabelsRef = linkLabels
  linkLabelBgRef = linkLabelBg

  // Nodes group
  const nodeGroup = g.append('g').attr('class', 'nodes')

  // Node circles
  const node = nodeGroup.selectAll('circle')
    .data(nodes)
    .enter().append('circle')
    .attr('r', 10)
    .attr('fill', d => getColor(d.type))
    .attr('stroke', 'var(--mono-50)')
    .attr('stroke-width', 2.5)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        // Only record position, don't restart simulation (distinguish click from drag)
        d.fx = d.x
        d.fy = d.y
        d._dragStartX = event.x
        d._dragStartY = event.y
        d._isDragging = false
      })
      .on('drag', (event, d) => {
        // Check if truly dragging (moved beyond threshold)
        const dx = event.x - d._dragStartX
        const dy = event.y - d._dragStartY
        const distance = Math.sqrt(dx * dx + dy * dy)

        if (!d._isDragging && distance > 3) {
          // First time detecting true drag, restart simulation
          d._isDragging = true
          simulation.alphaTarget(0.3).restart()
        }

        if (d._isDragging) {
          d.fx = event.x
          d.fy = event.y
        }
      })
      .on('end', (event, d) => {
        // Only stop simulation gradually if truly dragged
        if (d._isDragging) {
          simulation.alphaTarget(0)
        }
        d.fx = null
        d.fy = null
        d._isDragging = false
      })
    )
    .on('click', (event, d) => {
      event.stopPropagation()
      // Reset all node styles
      node.attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
      linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
      // Highlight selected node
      d3.select(event.target).attr('stroke', 'var(--accent)').attr('stroke-width', 4)
      // Highlight edges connected to this node
      link.filter(l => l.source.id === d.id || l.target.id === d.id)
        .attr('stroke', 'var(--accent)')
        .attr('stroke-width', 2.5)

      selectedItem.value = {
        type: 'node',
        data: d.rawData,
        entityType: d.type,
        color: getColor(d.type)
      }
    })
    .on('mouseenter', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', 'var(--fg-on-inverse)').attr('stroke-width', 3)
      }
    })
    .on('mouseleave', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
      }
    })

  // Node Labels
  const nodeLabels = nodeGroup.selectAll('text')
    .data(nodes)
    .enter().append('text')
    .text(d => d.name.length > 8 ? d.name.substring(0, 8) + '…' : d.name)
    .attr('font-size', '11px')
    .attr('fill', 'var(--fg-on-inverse)')
    .attr('font-weight', '500')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', 'system-ui, sans-serif')

  simulation.on('tick', () => {
    // Update curve paths
    link.attr('d', d => getLinkPath(d))

    // Update edge label positions (no rotation, horizontal is clearer)
    linkLabels.each(function(d) {
      const mid = getLinkMidpoint(d)
      d3.select(this)
        .attr('x', mid.x)
        .attr('y', mid.y)
        .attr('transform', '') // Remove rotation, keep horizontal
    })

    // Update edge label background
    linkLabelBg.each(function(d, i) {
      const mid = getLinkMidpoint(d)
      const textEl = linkLabels.nodes()[i]
      const bbox = textEl.getBBox()
      d3.select(this)
        .attr('x', mid.x - bbox.width / 2 - 4)
        .attr('y', mid.y - bbox.height / 2 - 2)
        .attr('width', bbox.width + 8)
        .attr('height', bbox.height + 4)
        .attr('transform', '') // Remove rotation
    })

    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)

    nodeLabels
      .attr('x', d => d.x)
      .attr('y', d => d.y)
  })

  // Click on blank area to close detail panel
  svg.on('click', () => {
    selectedItem.value = null
    node.attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
    linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
    linkLabelBg.attr('fill', 'var(--bg-inverse)')
    linkLabels.attr('fill', 'var(--fg-meta)')
  })
}

watch(() => props.graphData, () => {
  nextTick(renderGraph)
}, { deep: true })

// Issue #10 — re-render when the temporal-slider position changes.
watch(selectedRound, () => {
  nextTick(renderGraph)
})

// Watch edge label show/hide toggle
watch(showEdgeLabels, (newVal) => {
  if (linkLabelsRef) {
    linkLabelsRef.style('display', newVal ? 'block' : 'none')
  }
  if (linkLabelBgRef) {
    linkLabelBgRef.style('display', newVal ? 'block' : 'none')
  }
})

const handleResize = () => {
  nextTick(renderGraph)
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (currentSimulation) {
    currentSimulation.stop()
  }
})
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: var(--bg-elevated);
  background-image: radial-gradient(var(--mono-700) 1px, transparent 1px);
  background-size: 24px 24px;
  overflow: hidden;
}

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

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

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

/* Building hint — editorial pill on inverse surface */
.graph-building-hint {
  position: absolute;
  bottom: 160px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-inverse);
  color: var(--bg);
  padding: 8px 16px;
  border-radius: var(--r-pill);
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: var(--s-2);
  border: 1px solid var(--mono-200);
  z-index: 100;
}

.memory-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  animation: breathe 2s ease-in-out infinite;
}

.memory-icon {
  width: 14px;
  height: 14px;
  color: var(--accent);
}

@keyframes breathe {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

.graph-building-hint.finished-hint {
  background: var(--bg-inverse);
  border: 1px solid var(--mono-200);
}

.finished-hint .hint-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

.finished-hint .hint-icon {
  width: 14px;
  height: 14px;
  color: var(--bg);
}

.finished-hint .hint-text {
  flex: 1;
  white-space: nowrap;
}

.hint-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  background: transparent;
  border: 1px solid var(--mono-200);
  border-radius: 50%;
  cursor: pointer;
  color: var(--bg);
  transition: border-color 150ms ease, color 150ms ease;
  margin-left: var(--s-2);
  flex-shrink: 0;
}

.hint-close-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

/* Loading spinner */
.loading-spinner {
  width: 32px;
  height: 32px;
  border: 1.5px solid var(--rule);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto var(--s-3);
}

</style>
