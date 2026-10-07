/**
 * Testhilfen der bearbeitbaren Graph-Ansicht (#1808, Etappe 8).
 *
 * Der Graph mit Herkunftsmarken ist absichtlich eine Variante des Leser-
 * Fixtures: ein Knoten und eine Kante von Hand, der Rest extrahiert. Damit
 * prueft der Test, dass die Marke an genau den Elementen steht und nicht an
 * allen.
 */
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import { vi } from 'vitest'
import de from '@/i18n/locales/de.json'
import { GraphDataSchema, type GraphData } from '@/composables/graph-library/graphReaderModel'

export function editableGraphFixture(): GraphData {
  return GraphDataSchema.parse({
    graph_id: '11111111-1111-4111-8111-111111111111',
    nodes: [
      {
        uuid: '22222222-2222-4222-8222-222222222222',
        name: 'Kreistag',
        labels: ['Organisation'],
        entity_type: 'Organisation',
        summary: 'Beschlussgremium des Landkreises',
        attributes: { aliases: ['Kreisrat'] },
        created_at: '2026-10-01',
        provenance: { origin: null, episode_count: 2 },
      },
      {
        uuid: '33333333-3333-4333-8333-333333333333',
        name: 'Moorhagen',
        labels: ['Ort'],
        entity_type: 'Ort',
        created_at: null,
        provenance: { origin: null, episode_count: 0 },
      },
      {
        uuid: '44444444-4444-4444-8444-444444444444',
        name: 'Neues Buero',
        labels: ['Organisation'],
        entity_type: 'Organisation',
        summary: 'von Hand angelegt',
        created_at: '2026-10-07T09:00:00',
        provenance: { origin: 'manual', changed_at: '2026-10-07T09:00:00', episode_count: 0 },
      },
    ],
    edges: [
      {
        uuid: '55555555-5555-4555-8555-555555555555',
        name: 'TRIFFT_ENTSCHEIDUNG_ÜBER',
        fact: 'Der Kreistag entscheidet über Moorhagen.',
        source_node_uuid: '22222222-2222-4222-8222-222222222222',
        target_node_uuid: '33333333-3333-4333-8333-333333333333',
        episode_ids: ['ep1', 'ep2'],
        created_at: '2026-10-01',
        provenance: { origin: null, episode_count: 2 },
      },
      {
        uuid: '66666666-6666-4666-8666-666666666666',
        name: 'ARBEITET_IN',
        fact: 'Von Hand erfasst, danach im Text geaendert.',
        source_node_uuid: '44444444-4444-4444-8444-444444444444',
        target_node_uuid: '33333333-3333-4333-8333-333333333333',
        episode_ids: ['ep1'],
        created_at: '2026-10-01',
        provenance: { origin: 'edited', changed_at: '2026-10-07T10:00:00', episode_count: 1 },
      },
    ],
  })
}

export const SECOND_NODE = '33333333-3333-4333-8333-333333333333'
export const MANUAL_NODE = '44444444-4444-4444-8444-444444444444'
export const EXTRACTED_NODE = '22222222-2222-4222-8222-222222222222'
export const EDITED_EDGE = '66666666-6666-4666-8666-666666666666'
export const EXTRACTED_EDGE = '55555555-5555-4555-8555-555555555555'

export function makeI18n() {
  return createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
}

const Blank = { template: '<div />' }

export function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/library/graphs', name: 'LibraryGraphs', component: Blank },
      { path: '/graphs/:projectId', name: 'GraphLibraryDetail', component: Blank },
      { path: '/runs/:simulationId', name: 'RunOverview', component: Blank },
    ],
  })
}

export const focusSpy = vi.fn()

/** Ersatz fuer GraphCanvas: d3 laeuft in jsdom nicht. */
export const CanvasStub = defineComponent({
  name: 'GraphCanvas',
  props: { graphData: { type: Object, default: null }, entityTypes: { type: Array, default: () => [] }, hideDetail: Boolean },
  emits: ['select'],
  setup(props, { expose }) {
    expose({ focusTarget: focusSpy })
    return () =>
      h('div', {
        'data-testid': 'canvas-stub',
        'data-nodes': String((props.graphData as GraphData | null)?.nodes.length ?? 0),
        'data-dashed': String(
          ((props.graphData as GraphData | null)?.edges ?? [])
            .filter((edge) => {
              const origin = (edge as { provenance?: { origin?: string | null } }).provenance?.origin
              return origin === 'manual' || origin === 'edited'
            }).length,
        ),
      })
  },
})