/**
 * SimTabsBar — Slice UI-2b (#1713), docs/design/simulation-feed.md §2.1.
 *
 * Deckt ab:
 * 1. role="tablist"/role="tab", aria-current="page" auf dem aktiven Tab.
 * 2. Klick navigiert per router.push mit simulationId + aktueller Query.
 * 3. Tastatur: ArrowRight/ArrowLeft/Home/End wechseln den Fokus und navigieren.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const routerPush = vi.hoisted(() => vi.fn())
const route = vi.hoisted(() => ({ query: { projectId: 'project_42' } as Record<string, unknown> }))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => route,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import SimTabsBar from '../SimTabsBar.vue'

function mountBar(activeTab: 'pipeline' | 'feed' | 'threads' | 'rounds' | 'actions' = 'pipeline') {
  return mount(SimTabsBar, {
    props: { activeTab, simulationId: 'sim_x' },
    attachTo: document.body,
  })
}

describe('SimTabsBar', () => {
  beforeEach(() => {
    routerPush.mockClear()
    route.query = { projectId: 'project_42' }
  })

  it('rendert role=tablist mit fuenf role=tab-Buttons', () => {
    const w = mountBar()
    expect(w.attributes('role')).toBe('tablist')
    const tabs = w.findAll('[role="tab"]')
    expect(tabs).toHaveLength(5)
  })

  it('markiert den aktiven Tab mit aria-current=page', () => {
    const w = mountBar('rounds')
    const tabs = w.findAll('[role="tab"]')
    const active = tabs.find((t) => t.attributes('aria-current') === 'page')
    expect(active?.text()).toBe('feed.roundsTab')
  })

  it('Klick auf einen Tab navigiert per router.push mit Query', async () => {
    const w = mountBar('pipeline')
    const tabs = w.findAll('[role="tab"]')
    await tabs[2].trigger('click') // threads
    expect(routerPush).toHaveBeenCalledWith({
      name: 'SimThreads',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })

  it('Klick auf den bereits aktiven Tab navigiert nicht erneut', async () => {
    const w = mountBar('feed')
    const tabs = w.findAll('[role="tab"]')
    await tabs[1].trigger('click')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('ArrowRight wechselt Fokus und navigiert zum naechsten Tab', async () => {
    const w = mountBar('pipeline')
    const tabs = w.findAll('[role="tab"]')
    await tabs[0].trigger('keydown', { key: 'ArrowRight' })
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulationFeed',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })

  it('End springt zum letzten Tab (actions)', async () => {
    const w = mountBar('pipeline')
    const tabs = w.findAll('[role="tab"]')
    await tabs[0].trigger('keydown', { key: 'End' })
    expect(routerPush).toHaveBeenCalledWith({
      name: 'SimActions',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })

  it('Home springt zum ersten Tab (pipeline)', async () => {
    const w = mountBar('actions')
    const tabs = w.findAll('[role="tab"]')
    await tabs[4].trigger('keydown', { key: 'Home' })
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulation',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })
})
