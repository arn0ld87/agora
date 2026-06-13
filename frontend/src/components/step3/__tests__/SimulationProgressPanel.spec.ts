/**
 * SimulationProgressPanel — extracted from Step3Simulation (Issue #586).
 * Prüft: stat-Grid-Rendering, sim-clock-Anzeige, formatElapsed-Ausgabe.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import SimulationProgressPanel from '../SimulationProgressPanel.vue'

const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

const globalStubs = {
  Kicker: { template: '<span><slot /></span>' },
}

function mountComponent(props = {}) {
  return mount(SimulationProgressPanel, {
    props: {
      totalActions: 0,
      twitterActions: 0,
      redditActions: 0,
      ...props,
    },
    global: { plugins: [i18n], stubs: globalStubs },
  })
}

describe('SimulationProgressPanel (Issue #586)', () => {
  it('rendert drei stat-Einträge', () => {
    const wrapper = mountComponent({ totalActions: 42, twitterActions: 20, redditActions: 22 })
    const statValues = wrapper.findAll('.stat-value')
    expect(statValues).toHaveLength(3)
    expect(statValues[0].text()).toBe('42')
    expect(statValues[1].text()).toBe('20')
    expect(statValues[2].text()).toBe('22')
  })

  it('zeigt sim-clock wenn currentSimTime gesetzt ist', () => {
    const wrapper = mountComponent({
      totalActions: 10,
      twitterActions: 5,
      redditActions: 5,
      currentSimTime: new Date('2025-01-15T14:30:00Z'),
      simElapsedSec: 90,
    })
    expect(wrapper.find('.sim-clock').exists()).toBe(true)
    // Elapsed: 01:30
    expect(wrapper.find('.sim-clock').text()).toContain('01:30')
  })

  it('zeigt keine sim-clock wenn currentSimTime null', () => {
    const wrapper = mountComponent({ totalActions: 0, twitterActions: 0, redditActions: 0, currentSimTime: null })
    expect(wrapper.find('.sim-clock').exists()).toBe(false)
  })

  it('hat data-testid="simulation-progress-panel"', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('[data-testid="simulation-progress-panel"]').exists()).toBe(true)
  })
})
