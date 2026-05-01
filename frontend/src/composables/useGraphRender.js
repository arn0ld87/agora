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

import { onMounted, onUnmounted, ref, toValue, watch, nextTick } from 'vue'
import * as d3 from 'd3'

import { buildGraphRenderData } from '../components/graph/graphPanelData'
import { formatEdgeLabel } from '../components/graph/edgeLabelI18n'
import { getLinkMidpoint, getLinkPath } from '../components/graph/graphPanelGeometry'

/**
 * @param {object} args
 * @param {import('vue').Ref<SVGSVGElement|null>} args.svgRef          – Vue-Ref auf das `<svg>`-Element
 * @param {import('vue').Ref<HTMLElement|null>}   args.containerRef    – Vue-Ref auf den Container, dessen Maße den Viewport definieren
 * @param {import('vue').MaybeRefOrGetter<object|null>} args.graphData – Reactive Source mit `nodes`/`edges`
 * @param {import('vue').MaybeRefOrGetter<Array>}       args.entityTypes – Reactive Source mit Entity-Type-Liste (für Farb-Mapping)
 * @param {import('vue').Ref<boolean>}            args.showEdgeLabels  – Sichtbarkeit der Kantenbeschriftungen
 * @param {((key: string) => string)=}            args.translateLabel  – optionaler i18n-Hook (`vue-i18n` `t`); wird auf `edge.name` angewandt
 * @returns {{ selectedItem: import('vue').Ref<object|null>, render: () => void }}
 */
export function useGraphRender({ svgRef, containerRef, graphData, entityTypes, showEdgeLabels, translateLabel = null }) {
  const selectedItem = ref(null)

  let currentSimulation = null
  let linkLabelsRef = null
  let linkLabelBgRef = null

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
    const { nodes, edges, getColor } = buildGraphRenderData(data, types)
    if (nodes.length === 0) return

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
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

    const g = svg.append('g')

    svg.call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
      g.attr('transform', event.transform)
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
      .text(d => formatEdgeLabel(d.name, translateLabel))
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
      .call(d3.drag()
        .on('start', (event, d) => {
          d.fx = d.x
          d.fy = d.y
          d._dragStartX = event.x
          d._dragStartY = event.y
          d._isDragging = false
        })
        .on('drag', (event, d) => {
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
        .on('end', (event, d) => {
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
          .attr('x', mid.x - bbox.width / 2 - 4)
          .attr('y', mid.y - bbox.height / 2 - 2)
          .attr('width', bbox.width + 8)
          .attr('height', bbox.height + 4)
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

  return { selectedItem, render }
}
