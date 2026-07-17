<template>
  <div
    v-if="nodes.length > 0"
    class="graph-minimap"
    :aria-label="title"
    role="region"
  >
    <svg
      ref="miniSvg"
      class="minimap-svg"
      :viewBox="`0 0 ${MINIMAP_W} ${MINIMAP_H}`"
      preserveAspectRatio="xMidYMid meet"
      tabindex="0"
      :aria-label="title"
      role="application"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @pointerleave="onPointerLeave"
      @keydown="onKeydown"
    >
      <!-- Graph bounds frame -->
      <rect
        :x="padX"
        :y="padY"
        :width="Math.max(0, innerW)"
        :height="Math.max(0, innerH)"
        class="minimap-frame"
        rx="2"
      />

      <!-- Nodes (scaled) -->
      <circle
        v-for="n in minimapNodePoints"
        :key="n.id"
        :cx="n.mx"
        :cy="n.my"
        :r="1.4"
        class="minimap-node"
      />

      <!-- Viewport rectangle (what the main canvas currently shows) -->
      <rect
        v-if="viewportRect"
        :x="viewportRect.x"
        :y="viewportRect.y"
        :width="viewportRect.w"
        :height="viewportRect.h"
        class="minimap-viewport"
        rx="1"
      />
    </svg>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  /**
   * Mirror of node positions from useGraphRender.minimapNodes.
   * Shape: Array<{ id: string; x: number; y: number }>
   */
  nodes: { type: Array, default: () => [] },
  /**
   * Mirror of the main viewport's d3.zoom transform + container dims.
   * Shape: { x, y, k, width, height } where (x,y,k) is the zoom transform
   * (translate tx/ty + scale k) and width/height are the main canvas size.
   */
  viewport: {
    type: Object,
    default: () => ({ x: 0, y: 0, k: 1, width: 0, height: 0 }),
  },
  /** Accessible label (i18n-provided). */
  title: { type: String, default: 'Minimap' },
})

const emit = defineEmits(['seek'])

const MINIMAP_W = 168
const MINIMAP_H = 116
const PAD = 8

const padX = PAD
const padY = PAD
const innerW = MINIMAP_W - PAD * 2
const innerH = MINIMAP_H - PAD * 2

const miniSvg = ref(null)
const isDragging = ref(false)

// Graph-space bounding box of all nodes (with a small degenerate fallback).
const graphBounds = computed(() => {
  const ns = props.nodes
  if (!ns || ns.length === 0) {
    return { minX: 0, minY: 0, maxX: 1, maxY: 1 }
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of ns) {
    if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) continue
    if (n.x < minX) minX = n.x
    if (n.y < minY) minY = n.y
    if (n.x > maxX) maxX = n.x
    if (n.y > maxY) maxY = n.y
  }
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, maxX: 1, maxY: 1 }
  // Guard against degenerate (single-point / colinear) bounds.
  if (maxX - minX < 1) { minX -= 0.5; maxX += 0.5 }
  if (maxY - minY < 1) { minY -= 0.5; maxY += 0.5 }
  return { minX, minY, maxX, maxY }
})

const scale = computed(() => {
  const b = graphBounds.value
  const sx = innerW / Math.max(1e-6, b.maxX - b.minX)
  const sy = innerH / Math.max(1e-6, b.maxY - b.minY)
  // Uniform scale, fit-inside (use the smaller axis).
  return Math.min(sx, sy)
})

// Graph → Mini-Map pixel mapping.
function toMini(gx, gy) {
  const b = graphBounds.value
  const s = scale.value
  // Center within inner box (for the unused axis).
  const usedW = (b.maxX - b.minX) * s
  const usedH = (b.maxY - b.minY) * s
  const offX = padX + (innerW - usedW) / 2
  const offY = padY + (innerH - usedH) / 2
  return { mx: offX + (gx - b.minX) * s, my: offY + (gy - b.minY) * s }
}

// Mini-Map pixel → Graph-space (inverse of toMini).
function toGraph(mx, my) {
  const b = graphBounds.value
  const s = scale.value || 1e-6
  const usedW = (b.maxX - b.minX) * s
  const usedH = (b.maxY - b.minY) * s
  const offX = padX + (innerW - usedW) / 2
  const offY = padY + (innerH - usedH) / 2
  return { gx: (mx - offX) / s + b.minX, gy: (my - offY) / s + b.minY }
}

const minimapNodePoints = computed(() => {
  return props.nodes.map(n => {
    const p = toMini(n.x, n.y)
    return { id: n.id, mx: p.mx, my: p.my }
  })
})

// Viewport rectangle in graph space, then mapped to Mini-Map pixels.
// Visible graph region: left = -tx/k, top = -ty/k, w = width/k, h = height/k.
const viewportRect = computed(() => {
  const vp = props.viewport
  if (!vp || !vp.k || vp.k <= 0) return null
  const left = -vp.x / vp.k
  const top = -vp.y / vp.k
  const w = vp.width / vp.k
  const h = vp.height / vp.k
  const tl = toMini(left, top)
  const br = toMini(left + w, top + h)
  return {
    x: Math.min(tl.mx, br.mx),
    y: Math.min(tl.my, br.my),
    w: Math.abs(br.mx - tl.mx),
    h: Math.abs(br.my - tl.my),
  }
})

function pointerToGraph(event) {
  const el = miniSvg.value
  if (!el) return null
  const rect = el.getBoundingClientRect()
  // Map client coords into the SVG's viewBox coordinate space.
  const mx = ((event.clientX - rect.left) / rect.width) * MINIMAP_W
  const my = ((event.clientY - rect.top) / rect.height) * MINIMAP_H
  return toGraph(mx, my)
}

function onPointerDown(event) {
  isDragging.value = true
  if (event.target && typeof event.target.setPointerCapture === 'function') {
    event.target.setPointerCapture(event.pointerId)
  }
  const g = pointerToGraph(event)
  if (g) emit('seek', g)
}

function onPointerMove(event) {
  if (!isDragging.value) return
  const g = pointerToGraph(event)
  if (g) emit('seek', g)
}

function onPointerUp(event) {
  if (!isDragging.value) return
  isDragging.value = false
  if (event.target && typeof event.target.releasePointerCapture === 'function') {
    event.target.releasePointerCapture(event.pointerId)
  }
}

function onPointerLeave() {
  // Do NOT cancel on leave — pointer capture keeps the drag alive.
}

// Issue #744 Phase 4b — keyboard-operable minimap. Arrow keys pan the main
// viewport in 20 % steps of the currently visible region, Home/End jump to
// the horizontal bounds. CodeRabbit Major (F2): same seek functionality
// without a mouse.
const ARROW_MAP = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
}

function stepSeek(dx, dy) {
  const vp = props.viewport
  if (!vp || !vp.k || vp.k <= 0) return
  // Visible region in graph space: left = -tx/k, top = -ty/k,
  // w = width/k, h = height/k.
  const cx = (-vp.x + vp.width / 2) / vp.k
  const cy = (-vp.y + vp.height / 2) / vp.k
  const stepX = (vp.width / vp.k) * 0.2
  const stepY = (vp.height / vp.k) * 0.2
  emit('seek', { gx: cx + dx * stepX, gy: cy + dy * stepY })
}

function onKeydown(event) {
  const m = ARROW_MAP[event.key]
  if (m) {
    event.preventDefault()
    stepSeek(m[0], m[1])
    return
  }
  if (event.key === 'Home') {
    event.preventDefault()
    const b = graphBounds.value
    emit('seek', { gx: b.minX, gy: (b.minY + b.maxY) / 2 })
    return
  }
  if (event.key === 'End') {
    event.preventDefault()
    const b = graphBounds.value
    emit('seek', { gx: b.maxX, gy: (b.minY + b.maxY) / 2 })
    return
  }
}
</script>

<style scoped>
.graph-minimap {
  position: absolute;
  bottom: var(--s-5);
  right: var(--s-5);
  width: 168px;
  height: 116px;
  background: var(--surface-translucent, var(--bg));
  border: 1px solid var(--hairline, var(--rule));
  border-radius: var(--r-5, var(--r-1));
  box-shadow: var(--shadow-2, none);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  z-index: 10;
  overflow: hidden;
}

.minimap-svg {
  width: 100%;
  height: 100%;
  display: block;
  cursor: crosshair;
  touch-action: none;
}

.minimap-frame {
  fill: var(--bg-elevated, var(--bg));
  fill-opacity: 0.35;
  stroke: var(--hairline, var(--rule));
  stroke-width: 0.5;
}

.minimap-node {
  fill: var(--accent);
  fill-opacity: 0.8;
}

.minimap-viewport {
  fill: var(--accent);
  fill-opacity: 0.08;
  stroke: var(--accent);
  stroke-width: 1;
  stroke-opacity: 0.9;
  pointer-events: none;
}
</style>