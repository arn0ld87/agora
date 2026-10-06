import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import RunSimulationView from '../simulation/RunSimulationView.vue'
import RunTabs from '@/components/run/RunTabs.vue'
import { deriveRunTabs } from '@/composables/run/runTabs'
import de from '@/i18n/locales/de.json'

const Stub = defineComponent({ render: () => h('div', { 'data-testid': 'child' }) })

function build() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/simulations/:simulationId', name: 'RunOverview', component: Stub },
      { path: '/simulations/:simulationId/graph', name: 'RunGraph', component: Stub },
      { path: '/v4/simulation/:simulationId/interviews', name: 'RunInterviewsLegacy', component: Stub },
      {
        path: '/simulations/:simulationId/simulation',
        name: 'RunSimulation',
        component: RunSimulationView,
        props: true,
        children: [
          { path: 'feed/:network(twitter|reddit)?', name: 'RunSimulationFeed', component: Stub },
          { path: 'post/:postId', name: 'RunSimulationPost', component: Stub },
          { path: 'rounds', name: 'RunSimulationRounds', component: Stub },
          { path: 'diagnostics', name: 'RunSimulationDiagnostics', component: Stub },
        ],
      },
    ],
  })
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  return { router, i18n }
}

async function mountAt(path: string) {
  const { router, i18n } = build()
  await router.push(path)
  await router.isReady()
  const w = mount(
    defineComponent({ render: () => h('div', [h(RunTabs, { tabs: deriveRunTabs({ simulationId: 'sim_1', projectId: null, latestReportId: null }) }), h(RouterView)]) }),
    { global: { plugins: [router, i18n] } },
  )
  await flushPromises()
  return { router, w }
}

describe('RunSimulationView', () => {
  it('zeigt Feed · Runden · Diagnose als Navigation mit Kopf-Bereich', async () => {
    const { w } = await mountAt('/simulations/sim_1/simulation/feed')
    const nav = w.get('[data-testid="run-sim-tabs"]')
    expect(nav.element.tagName).toBe('NAV')
    expect(nav.attributes('aria-label')).toBe('Ansichten der Simulation')
    expect(nav.findAll('a').map((a) => a.text())).toEqual(['Feed', 'Runden', 'Diagnose'])
    const slot = w.get('[data-testid="run-sim-header-slot"]')
    expect(slot.element.children.length).toBe(0)
    expect(w.find('[data-testid="child"]').exists()).toBe(true)
  })

  it.each([
    ['/simulations/sim_1/simulation/feed', 'feed'],
    ['/simulations/sim_1/simulation/feed/reddit', 'feed'],
    ['/simulations/sim_1/simulation/post/twitter:123', 'feed'],
    ['/simulations/sim_1/simulation/rounds', 'rounds'],
    ['/simulations/sim_1/simulation/diagnostics', 'diagnostics'],
  ])('%s: aria-current="page" nur an %s', async (path, key) => {
    const { w } = await mountAt(path)
    const current = w.findAll('[data-testid="run-sim-tabs"] a[aria-current="page"]')
    expect(current.map((a) => a.attributes('data-testid'))).toEqual([`run-sim-tab-${key}`])
  })

  it('Links tragen die eigenen Adressen', async () => {
    const { w } = await mountAt('/simulations/sim_1/simulation/feed')
    const hrefs = w.findAll('[data-testid="run-sim-tabs"] a').map((a) => a.attributes('href'))
    expect(hrefs).toEqual([
      '/simulations/sim_1/simulation/feed',
      '/simulations/sim_1/simulation/rounds',
      '/simulations/sim_1/simulation/diagnostics',
    ])
  })

  it('Reiter „Simulation“ des Laufs bleibt auf allen Unterreitern aktiv', async () => {
    for (const path of ['/simulations/sim_1/simulation/rounds', '/simulations/sim_1/simulation/post/reddit:comment:7']) {
      const { w } = await mountAt(path)
      const sim = w.get('[data-testid="run-tab-simulation"]')
      expect(sim.attributes('aria-current')).toBe('page')
    }
  })
})
