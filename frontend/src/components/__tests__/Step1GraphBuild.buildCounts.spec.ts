import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

/**
 * UAT-011 (2026-10-09, armserver) — „Graphabschluss zeigt falsche Zähler".
 *
 * Die Abschlusskarte koppelte ihre Zähler ausschließlich an graphData aus
 * einem einzelnen GET /api/graph/data, das erst NACH dem Phase-2-Wechsel
 * beginnt. Im Fenster bis zur Antwort standen harte 0en unter einem
 * „Fertig"-Badge — in der UAT las der Tester „0 Entitäten / 0 Beziehungen"
 * zu einem Zeitpunkt, an dem Neo4j längst 12/15 trug.
 *
 * Fix-Vertrag: Die autoritativen Counts aus dem Task-Ergebnis
 * (task.result.node_count/edge_count, Worker-Read zum Completion-Zeitpunkt)
 * werden sofort gezeigt; fehlt jede Quelle, ist die Zählung ausdrücklich
 * als ausstehend gekennzeichnet — nie mehr eine schlichte 0.
 */

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ name: 'StepGraphBuild', params: {}, query: {} }),
}))
vi.mock('../../api/simulation', () => ({ createSimulation: vi.fn() }))

import Step1GraphBuild from '../Step1GraphBuild.vue'

function mountStep(props: Record<string, unknown>) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  return mount(Step1GraphBuild, {
    props: {
      currentPhase: 2,
      projectData: { project_id: 'p1', graph_id: 'g1' },
      systemLogs: [],
      ...props,
    },
    global: {
      plugins: [i18n],
      stubs: {
        Kicker: { template: '<span><slot /></span>' },
        Badge: { template: '<span class="badge"><slot /></span>' },
        Button: {
          props: ['disabled', 'loading', 'variant', 'arrow'],
          template: '<button :disabled="disabled"><slot /></button>',
        },
      },
    },
  })
}

function statValues(wrapper: ReturnType<typeof mountStep>) {
  return wrapper.findAll('.stat-value').map((node) => node.text())
}

describe('Step1GraphBuild — Abschlusszähler (UAT-011)', () => {
  it('zeigt die Counts aus dem Task-Ergebnis, bevor die Graphdaten geladen sind', () => {
    const wrapper = mountStep({
      graphData: null,
      buildCounts: { node_count: 12, edge_count: 15 },
    })
    const values = statValues(wrapper)
    expect(values[0]).toBe('12')
    expect(values[1]).toBe('15')
    expect(wrapper.find('.stats-pending').exists()).toBe(false)
  })

  it('kennzeichnet die Zählung als ausstehend, solange keine Quelle vorliegt', () => {
    const wrapper = mountStep({ graphData: null, buildCounts: null })
    const values = statValues(wrapper)
    expect(values[0]).toBe('–')
    expect(values[1]).toBe('–')
    expect(wrapper.find('.stats-pending').exists()).toBe(true)
    expect(wrapper.text()).toContain('Zählung läuft')
  })

  it('zeigt die live geladenen Graphdaten, sobald sie vorliegen', () => {
    const wrapper = mountStep({
      graphData: { node_count: 12, edge_count: 15, nodes: [], edges: [] },
      buildCounts: null,
    })
    const values = statValues(wrapper)
    expect(values[0]).toBe('12')
    expect(values[1]).toBe('15')
    expect(wrapper.find('.stats-pending').exists()).toBe(false)
  })

  it('bleibt bei einem echten leeren Graphen bei 0, kennzeichnet aber nicht als ausstehend', () => {
    // node_count 0 aus geladenen Graphdaten ist ein echtes Ergebnis (das
    // Qualitätsgate blockiert ohnehin) — kein Zählfenster mehr.
    const wrapper = mountStep({
      graphData: { node_count: 0, edge_count: 0, nodes: [], edges: [] },
      buildCounts: { node_count: 0, edge_count: 0 },
    })
    const values = statValues(wrapper)
    expect(values[0]).toBe('0')
    expect(values[1]).toBe('0')
    expect(wrapper.find('.stats-pending').exists()).toBe(false)
  })
})
