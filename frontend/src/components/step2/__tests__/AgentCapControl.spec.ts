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

  it('Range und Zahlenfeld haben ein echtes label-for (#1799)', () => {
    const wrapper = mountComponent({ useAgentCap: true })
    const expected = { 'input[type="range"]': 'step2.agentCap.sliderLabel', 'input[type="number"]': 'step2.agentCap.numberLabel' }
    for (const [sel, key] of Object.entries(expected)) {
      const el = wrapper.find(sel)
      const id = el.attributes('id')
      expect(id).toBeTruthy()
      const label = wrapper.find(`label[for="${id}"]`)
      expect(label.exists()).toBe(true)
      expect(label.text()).toBe(key)
      const hintId = el.attributes('aria-describedby')
      expect(wrapper.find(`[id="${hintId}"]`).text()).toBe('step2.agentCap.minimumHint')
    }
  })
})

/**
 * UAT-001 — Der Dialog nannte als einzige Mindestzahl 10 (Untergrenze des
 * Feldes) und nie die Schwelle, an der der Bericht gemessen wird. Der Lauf
 * endete mit „18/20 Personas vorhanden" und ohne Berichtstext.
 */
describe('AgentCapControl — wirksame Persona-Schwelle (UAT-001)', () => {
  const messages = {
    de: {
      step2: {
        agentCap: {
          label: 'Max. Anzahl Agenten begrenzen',
          sliderLabel: 'Personas-Obergrenze, Schieberegler',
          numberLabel: 'Personas-Obergrenze, Zahl',
          unit: 'Agenten',
          minimumHint: 'Die Obergrenze muss mindestens 10 Agenten betragen.',
          unlimitedHint: 'Ohne Begrenzung …',
          reportFloor: 'Für einen Bericht braucht die DACH-Persona-Tabelle mindestens {floor} Agenten.',
        },
      },
    },
    en: {},
  }
  const realI18n = createI18n({
    legacy: false,
    locale: 'de',
    missingWarn: false,
    fallbackWarn: false,
    messages,
  })

  function mountWithMessages(props: Record<string, unknown>) {
    return mount(AgentCapControl, {
      props: { useAgentCap: false, maxAgents: 50, ...props },
      global: { plugins: [realI18n] },
    })
  }

  it('nennt ohne Obergrenze die Contract-Schwelle 20', () => {
    const wrapper = mountWithMessages({ useAgentCap: false })
    expect(wrapper.get('[data-testid="agent-cap-report-floor"]').text()).toContain('20')
  })

  it('nennt mit Obergrenze 10 die gesenkte Schwelle 10', () => {
    const wrapper = mountWithMessages({ useAgentCap: true, maxAgents: 10 })
    expect(wrapper.get('[data-testid="agent-cap-report-floor"]').text()).toContain('10')
  })

  it('nennt mit Obergrenze 30 weiterhin 20 (Contract deckelt)', () => {
    const wrapper = mountWithMessages({ useAgentCap: true, maxAgents: 30 })
    const text = wrapper.get('[data-testid="agent-cap-report-floor"]').text()
    expect(text).toContain('20')
    expect(text).not.toContain('30')
  })
})
