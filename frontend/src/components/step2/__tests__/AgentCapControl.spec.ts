/**
 * AgentCapControl — extracted from Step2EnvSetup (Issue #586).
 * Prüft: Checkbox-Toggle, Slider-Rendering, Warn-Banner, und
 * unlimitedHint-Anzeige. Deckt die Acceptance-Criteria "new spec per
 * extracted child component" ab.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AgentCapControl from '../AgentCapControl.vue'

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

function mountComponent(props = {}) {
  return mount(AgentCapControl, {
    props: {
      useAgentCap: false,
      maxAgents: 50,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('AgentCapControl (Issue #586)', () => {
  it('rendert Checkbox', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(true)
  })

  it('zeigt Slider und Number-Input wenn useAgentCap=true', () => {
    const wrapper = mountComponent({ useAgentCap: true, maxAgents: 50 })
    expect(wrapper.find('input[type="range"]').exists()).toBe(true)
    expect(wrapper.find('input[type="number"]').exists()).toBe(true)
  })

  it('zeigt keinen Slider wenn useAgentCap=false', () => {
    const wrapper = mountComponent({ useAgentCap: false })
    expect(wrapper.find('input[type="range"]').exists()).toBe(false)
  })

  it('emittiert update:useAgentCap beim Checkbox-Wechsel', async () => {
    const wrapper = mountComponent({ useAgentCap: false })
    await wrapper.find('input[type="checkbox"]').setValue(true)
    expect(wrapper.emitted('update:useAgentCap')).toBeTruthy()
  })

  it('zeigt belowQuotaWarning-Banner wenn belowQuotaWarning=true', () => {
    const wrapper = mountComponent({
      useAgentCap: true,
      maxAgents: 10,
      belowQuotaWarning: true,
      quotaTotal: 20,
    })
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })

  it('zeigt unlimitedHint wenn useAgentCap=false', () => {
    const wrapper = mountComponent({ useAgentCap: false })
    // hint-Paragraph mit i18n-Key "step2.agentCap.unlimitedHint" wird gerendert
    const hints = wrapper.findAll('p.hint')
    expect(hints.length).toBeGreaterThanOrEqual(1)
  })

  it('Slider hat min=10 (Persona-Pool-Floor)', () => {
    const wrapper = mountComponent({ useAgentCap: true, maxAgents: 50 })
    expect(wrapper.find('input[type="range"]').attributes('min')).toBe('10')
  })
})
