/**
 * SimulationToolPanel — extracted from Step3Simulation (Issue #586).
 * Prüft: Filter-Buttons, Fehler-Zeilen-Styling, leere Zustände.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import SimulationToolPanel from '../SimulationToolPanel.vue'

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
  Badge: { template: '<span><slot /></span>' },
  StickyScrollBanner: { template: '<div />' },
}

function mountComponent(props = {}) {
  return mount(SimulationToolPanel, {
    props: {
      consoleLogs: [],
      toolPanelFilter: 'all',
      filteredConsoleLogs: [],
      consoleUnreadCount: 0,
      ...props,
    },
    global: { plugins: [i18n], stubs: globalStubs },
  })
}

describe('SimulationToolPanel (Issue #586)', () => {
  it('hat data-testid="simulation-tool-panel"', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('[data-testid="simulation-tool-panel"]').exists()).toBe(true)
  })

  it('zeigt 2 Filter-Buttons (all / errors)', () => {
    const wrapper = mountComponent()
    const btns = wrapper.findAll('.filter-btn')
    expect(btns).toHaveLength(2)
  })

  it('emittiert update:toolPanelFilter beim Klick auf errors-Button', async () => {
    const wrapper = mountComponent({ toolPanelFilter: 'all' })
    const errorBtn = wrapper.findAll('.filter-btn')[1]
    await errorBtn.trigger('click')
    const emitted = wrapper.emitted('update:toolPanelFilter')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['errors'])
  })

  it('rendert Logzeilen in der gefilterten Liste', () => {
    const lines = ['INFO: foo', 'ERROR: bar']
    const wrapper = mountComponent({
      consoleLogs: lines,
      filteredConsoleLogs: lines,
    })
    const entries = wrapper.findAll('.console-line')
    expect(entries).toHaveLength(2)
  })

  it('markiert Fehlerzeilen mit is-error', () => {
    const lines = ['ERROR: something failed', 'INFO: ok']
    const wrapper = mountComponent({
      consoleLogs: lines,
      filteredConsoleLogs: lines,
    })
    const errorEntries = wrapper.findAll('.console-line.is-error')
    expect(errorEntries).toHaveLength(1)
  })

  it('emittiert copy-line beim Klick auf Copy-Button', async () => {
    const lines = ['INFO: test line']
    const wrapper = mountComponent({
      consoleLogs: lines,
      filteredConsoleLogs: lines,
    })
    await wrapper.find('.copy-btn').trigger('click')
    expect(wrapper.emitted('copy-line')).toBeTruthy()
  })
})
