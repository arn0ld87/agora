import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import { vi } from 'vitest'
import de from '@/i18n/locales/de.json'
import { GraphDataSchema, type GraphData } from '@/composables/graph-library/graphReaderModel'
import type { Project } from '@/contracts/projectContract'

export function graphFixture(): GraphData {
  return GraphDataSchema.parse({
    graph_id: 'graph_1',
    node_count: 4,
    edge_count: 3,
    nodes: [
      { uuid: 'n1', name: 'Kreistag', labels: ['Organisation'], summary: 'Beschlussgremium des Landkreises', attributes: { aliases: ['Kreisrat'], sitz: 'Hollerau' }, created_at: '2026-10-01' },
      { uuid: 'n2', name: 'Moorhagen', labels: ['Ort'], summary: '', attributes: {}, created_at: null },
      { uuid: 'n3', name: 'Anna Berg', labels: ['Person'], summary: 'Hebamme', attributes: {}, created_at: null },
      { uuid: 'n4', name: 'Bernd Voss', labels: ['Person'], summary: '', attributes: {}, created_at: null },
    ],
    edges: [
      { uuid: 'e1', name: 'TRIFFT_ENTSCHEIDUNG_ÜBER', fact: 'Der Kreistag entscheidet über Moorhagen.', source_node_uuid: 'n1', target_node_uuid: 'n2', episode_ids: ['ep1', 'ep2'], created_at: null },
      { uuid: 'e2', name: 'ARBEITET_IN', fact: '', source_node_uuid: 'n3', target_node_uuid: 'n2', episode_ids: ['ep2'], created_at: null },
      { uuid: 'e3', name: 'KENNT', fact: '', source_node_uuid: 'n3', target_node_uuid: 'n4', episode_ids: [], created_at: null },
    ],
  })
}

export function projectFixture(over: Partial<Project> = {}): Project {
  return {
    project_id: 'proj_1',
    name: 'Geburtshilfe Hollerau',
    status: 'graph_completed',
    created_at: '2026-10-01T10:00:00',
    updated_at: '2026-10-02T10:00:00',
    files: [{ filename: 'seed.md', size: 10 }],
    total_text_length: 10,
    ontology: null,
    analysis_summary: null,
    graph_id: 'graph_1',
    graph_build_task_id: null,
    simulation_requirement: null,
    chunk_size: 500,
    chunk_overlap: 50,
    llm_model: null,
    llm_provider: null,
    llm_profile_id: null,
    ai_model_ref: null,
    error: null,
    ...over,
  }
}

export function makeI18n() {
  return createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
}

const Blank = { template: '<div />' }

export function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/library/graphs', name: 'LibraryGraphs', component: Blank },
      { path: '/library/runs', name: 'LibraryRuns', component: Blank },
      { path: '/graphs/:projectId', name: 'GraphLibraryDetail', component: Blank },
      { path: '/simulations/:simulationId', name: 'RunOverview', component: Blank },
      { path: '/simulations/:simulationId/graph', name: 'RunGraph', component: Blank },
      { path: '/v4/graph-build/:projectId', name: 'StepGraphBuild', component: Blank },
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
    return () => h('div', { 'data-testid': 'canvas-stub', 'data-nodes': String((props.graphData as GraphData | null)?.nodes.length ?? 0) })
  },
})
