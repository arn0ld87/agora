/**
 * useGraphRender — D3-Force-basiertes Rendering für den Agora-Graph.
 *
 * Issue #35 (EPIC-04-ST-02): hebt die D3-Renderlogik aus `GraphCanvas.vue`
 * heraus, damit sie separat test- und wartbar wird. Das Composable
 * ownst den Render-Lifecycle (mount/unmount/resize), hält die internen
 * D3-Refs (`currentSimulation`, `linkLabelsRef`, `linkLabelBgRef`) als
 * Modul-State pro Aufruf, watcht die reaktiven Eingaben (`graphData`,
 * `showEdgeLabels`) und stellt `selectedItem` als Output-Ref zur Verfügung.
 *
 * Schnittstellen (Issue-Akzeptanz):
 *  - Resize:    Composable registriert `window.resize` → `nextTick(renderGraph)`,
 *               cleanup in `onUnmounted`.
 *  - Re-Render: Watch auf `graphData` (deep) und `selectedRound`/`showEdgeLabels`
 *               wird vom Composable verdrahtet; Erst-Render in `onMounted`.
 *  - Selection: `selectedItem`-Ref wird vom Composable zurückgegeben; D3-Click-
 *               Handler schreiben hinein, der Aufrufer kann sie auch von außen
 *               leeren (z.B. bei „Detail schließen").
 */

import { onMounted, onUnmounted, ref, toValue, watch, nextTick, type MaybeRefOrGetter, type Ref } from 'vue'
import * as d3 from 'd3'

import { buildGraphRenderData } from '../components/graph/graphPanelData'
import { formatEdgeLabel } from '../components/graph/edgeLabelI18n'
import { getLinkMidpoint, getLinkPath } from '../components/graph/graphPanelGeometry'

/** Raw graph data shape consumed by buildGraphRenderData. */
interface RawGraphData {
  nodes?: Record<string, unknown>[]
  edges?: Record<string, unknown>[]
}

/** Entity-type color-mapping entry as expected by buildGraphRenderData. */
export interface EntityTypeEntry {
  name: string
  color: string
}

export interface UseGraphRenderArgs {
  svgRef: Ref<SVGSVGElement | null>
  containerRef: Ref<HTMLElement | null>
  graphData: MaybeRefOrGetter<RawGraphData | null>
  entityTypes: MaybeRefOrGetter<EntityTypeEntry[]>
  showEdgeLabels: Ref<boolean>
  translateLabel?: ((key: string) => string) | null
}

export interface UseGraphRenderReturn {
  selectedItem: Ref<Record<string, unknown> | null>
  render: () => void
  isPaused: Ref<boolean>
  pauseSimulation: () => void
  resumeSimulation: () => void
  togglePause: () => void
}

// reason: d3 v7 ships types via @types/d3; its internal Selection/Simulation generics require
// matching the exact datum types from graphPanelData.js (a JS file, checkJs=false).
// Using `any` here is the pragmatic choice to avoid sprawling casts across every d3 call.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D3Selection = d3.Selection<any, any, any, any>
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D3Simulation = d3.Simulation<any, any>

export function useGraphRender({
  svgRef,
  containerRef,
  graphData,
  entityTypes,
  showEdgeLabels,
  translateLabel = null,
}: UseGraphRenderArgs): UseGraphRenderReturn {
  const selectedItem = ref<Record<string, unknown> | null>(null)
  const isPaused = ref(false)

  let currentSimulation: D3Simulation | null = null
  let linkLabelsRef: D3Selection | null = null
  let linkLabelBgRef: D3Selection | null = null

  const render = () => {
    const svgEl = svgRef.value
    const data = toValue(graphData)
    if (!svgEl || !data) return

    if (currentSimulation) {
      currentSimulation.stop()
    }

    const container = containerRef.value
    if (!container) return
    const width = container.clientWidth
    const height = container.clientHeight

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)

    svg.selectAll('*').remove()

    const types = toValue(entityTypes) || []
    // reason: buildGraphRenderData is a JS function; the result types are inferred
    // as JSDoc-only and are not compatible with d3 SimulationNodeDatum generics.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { nodes, edges, getColor } = buildGraphRenderData(data, types) as { nodes: any[]; edges: any[]; getColor: (type: string) => string }
    if (nodes.length === 0) return

    // reason: nodes/edges come from a JS module; cast to any[] is required to satisfy d3 overloads
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const simulation: D3Simulation = (d3.forceSimulation as any)(nodes)
      .force('link', d3.forceLink(edges).id((d: any) => d.id).distance((d: any) => {
        const baseDistance = 150
        const edgeCount = d.pairTotal || 1
        return baseDistance + (edgeCount - 1) * 50
      }))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(50))
      .force('x', d3.forceX(width / 2).strength(0.04))
      .force('y', d3.forceY(height / 2).strength(0.04))

    currentSimulation = simulation
    if (isPaused.value) {
      // Vor dem Re-Render war pausiert → Simulation gar nicht erst loslaufen lassen.
      simulation.stop()
    }

    const g = svg.append('g')

    // Edge-Labels werden bei sehr weit rausgezoomtem Graph automatisch ausgeblendet,
    // damit dichte Stellen lesbar bleiben. Schwelle bewusst niedrig (0.6), damit normales
    // Zoomverhalten die Labels nicht plötzlich verliert. Toggle-State dominiert weiterhin.
    const EDGE_LABEL_AUTO_HIDE_ZOOM = 0.6
    let _zoomedOut = false

    // reason: d3.zoom() requires Selection<Element,...> but d3.select(svgEl) returns
    // Selection<SVGSVGElement,...>; cast is safe because SVGSVGElement extends Element.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(svg as any).call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event: any) => {
      g.attr('transform', event.transform)
      const wantsHide = event.transform.k < EDGE_LABEL_AUTO_HIDE_ZOOM
      if (wantsHide !== _zoomedOut) {
        _zoomedOut = wantsHide
        const visible = showEdgeLabels.value && !_zoomedOut
        if (linkLabelsRef) linkLabelsRef.style('display', visible ? 'block' : 'none')
        if (linkLabelBgRef) linkLabelBgRef.style('display', visible ? 'block' : 'none')
      }
    }))

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
        linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
        linkLabelBg.attr('fill', 'var(--bg-inverse)')
        linkLabels.attr('fill', 'var(--fg-meta)')
        d3.select(event.target).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)

        selectedItem.value = {
          type: 'edge',
          data: d.rawData,
        }
      })

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
        link.filter(l => l === d).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)
        d3.select(event.target).attr('fill', 'var(--plasma-soft)')

        selectedItem.value = {
          type: 'edge',
          data: d.rawData,
        }
      })

    const linkLabels = linkGroup.selectAll('text')
      .data(edges)
      .enter().append('text')
      // reason: formatEdgeLabel is JS (checkJs=false); translateLabel null triggers TS type error
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .text((d: any) => formatEdgeLabel(d.name, translateLabel as any))
      .attr('font-size', '12px')
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
        link.filter(l => l === d).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)
        d3.select(event.target).attr('fill', 'var(--plasma-400)')

        selectedItem.value = {
          type: 'edge',
          data: d.rawData,
        }
      })

    linkLabelsRef = linkLabels
    linkLabelBgRef = linkLabelBg

    const nodeGroup = g.append('g').attr('class', 'nodes')

    const node = nodeGroup.selectAll('circle')
      .data(nodes)
      .enter().append('circle')
      .attr('r', 10)
      .attr('fill', d => getColor(d.type))
      .attr('stroke', 'var(--mono-50)')
      .attr('stroke-width', 2.5)
      .style('cursor', 'pointer')
      // reason: d3.drag() requires Selection<Element,...>; GraphNodeViewModel from
      // a JS module does not satisfy d3's datum constraints — cast is safe at runtime.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .call((d3.drag() as any)
        .on('start', (event: any, d: any) => {
          d.fx = d.x
          d.fy = d.y
          d._dragStartX = event.x
          d._dragStartY = event.y
          d._isDragging = false
        })
        .on('drag', (event: any, d: any) => {
          const dx = event.x - d._dragStartX
          const dy = event.y - d._dragStartY
          const distance = Math.sqrt(dx * dx + dy * dy)

          if (!d._isDragging && distance > 3) {
            d._isDragging = true
            simulation.alphaTarget(0.3).restart()
          }

          if (d._isDragging) {
            d.fx = event.x
            d.fy = event.y
          }
        })
        .on('end', (event: any, d: any) => {
          if (d._isDragging) {
            simulation.alphaTarget(0)
          }
          d.fx = null
          d.fy = null
          d._isDragging = false
        }),
      )
      .on('click', (event, d) => {
        event.stopPropagation()
        node.attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
        linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
        d3.select(event.target).attr('stroke', 'var(--accent)').attr('stroke-width', 4)
        link.filter(l => l.source.id === d.id || l.target.id === d.id)
          .attr('stroke', 'var(--accent)')
          .attr('stroke-width', 2.5)

        selectedItem.value = {
          type: 'node',
          data: d.rawData,
          entityType: d.type,
          color: getColor(d.type),
        }
      })
      .on('mouseenter', (event: any, d: any) => {
        // reason: d.rawData is typed as `object` from JSDoc; index access via any is safe
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const dataUuid = (selectedItem.value?.data as any)?.uuid
        if (!selectedItem.value || dataUuid !== (d.rawData as any).uuid) {
          d3.select(event.target).attr('stroke', 'var(--fg-on-inverse)').attr('stroke-width', 3)
        }
      })
      .on('mouseleave', (event: any, d: any) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const dataUuid = (selectedItem.value?.data as any)?.uuid
        if (!selectedItem.value || dataUuid !== (d.rawData as any).uuid) {
          d3.select(event.target).attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
        }
      })

    // Knoten-Label: bis 14 Zeichen voll, sonst Trunkation mit Ellipsis. Voller Name
    // bleibt im SVG-`<title>` als nativer Browser-Tooltip erreichbar (Issue #129 SUB2).
    const NODE_LABEL_MAX = 14
    const nodeLabels = nodeGroup.selectAll('text')
      .data(nodes)
      .enter().append('text')
      .text(d => d.name.length > NODE_LABEL_MAX ? d.name.substring(0, NODE_LABEL_MAX) + '…' : d.name)
      .attr('font-size', '11px')
      .attr('fill', 'var(--fg-on-inverse)')
      .attr('font-weight', '500')
      .attr('dx', 14)
      .attr('dy', 4)
      .style('pointer-events', 'none')
      .style('font-family', 'system-ui, sans-serif')

    nodeLabels.append('title').text(d => d.name)
    node.append('title').text(d => d.name)

    simulation.on('tick', () => {
      link.attr('d', d => getLinkPath(d))

      linkLabels.each(function (d) {
        const mid = getLinkMidpoint(d)
        d3.select(this)
          .attr('x', mid.x)
          .attr('y', mid.y)
          .attr('transform', '')
      })

      linkLabelBg.each(function (d, i) {
        const mid = getLinkMidpoint(d)
        const textEl = linkLabels.nodes()[i]
        const bbox = textEl.getBBox()
        d3.select(this)
          .attr('x', mid.x - bbox.width / 2 - 6)
          .attr('y', mid.y - bbox.height / 2 - 3)
          .attr('width', bbox.width + 12)
          .attr('height', bbox.height + 6)
          .attr('transform', '')
      })

      node
        .attr('cx', d => d.x)
        .attr('cy', d => d.y)

      nodeLabels
        .attr('x', d => d.x)
        .attr('y', d => d.y)
    })

    svg.on('click', () => {
      selectedItem.value = null
      node.attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
      linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'var(--bg-inverse)')
      linkLabels.attr('fill', 'var(--fg-meta)')
    })
  }

  // Re-Render bei Datenwechsel (round-gefilterter Graph)
  watch(
    () => toValue(graphData),
    () => nextTick(render),
    { deep: true },
  )

  // Edge-Label-Sichtbarkeit live umschalten ohne Neuaufbau
  watch(showEdgeLabels, (newVal) => {
    if (linkLabelsRef) {
      linkLabelsRef.style('display', newVal ? 'block' : 'none')
    }
    if (linkLabelBgRef) {
      linkLabelBgRef.style('display', newVal ? 'block' : 'none')
    }
  })

  const handleResize = () => nextTick(render)

  onMounted(() => {
    window.addEventListener('resize', handleResize)
    nextTick(render)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    if (currentSimulation) {
      currentSimulation.stop()
      currentSimulation = null
    }
  })

  /**
   * Pause/Resume der laufenden Force-Simulation. Issue #129 SUB3:
   * Während des Graph-Aufbaus ist die Animation oft hektisch — Pause
   * friert die aktuelle Position ein, Resume nimmt den Layout-Fluss
   * wieder auf (schwacher Alpha, damit nichts springt).
   */
  function pauseSimulation() {
    isPaused.value = true
    if (currentSimulation) currentSimulation.stop()
  }

  function resumeSimulation() {
    isPaused.value = false
    if (currentSimulation) {
      currentSimulation.alpha(0.3).alphaTarget(0).restart()
    }
  }

  function togglePause() {
    if (isPaused.value) resumeSimulation()
    else pauseSimulation()
  }

  return {
    selectedItem,
    render,
    isPaused,
    pauseSimulation,
    resumeSimulation,
    togglePause,
  }
}
