import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

const h_ = await vi.hoisted(async () => {
  const { ref } = await import('vue')
  return {
    control: {
      busy: ref<string | null>(null),
      error: ref<string | null>(null),
      start: vi.fn(),
      plannedModel: vi.fn(),
    },
  }
})
vi.mock('@/composables/run/simulation/useSimulationControl', () => ({ useSimulationControl: () => h_.control }))

import RunSimEmptyState from '../RunSimEmptyState.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
const mountIt = (props: Record<string, unknown> = {}) =>
  mount(RunSimEmptyState, { props: { simulationId: 'sim_1', ...props }, global: { plugins: [i18n] } })

beforeEach(() => {
  h_.control.busy.value = null
  h_.control.error.value = null
  h_.control.start.mockReset()
  h_.control.plannedModel.mockReturnValue('std-model')
})

describe('RunSimEmptyState', () => {
  it('erklärt in zwei Sätzen (synthetisch, keine Vorhersage), zeigt das Modell als Text und den Startknopf', () => {
    const w = mountIt()
    const text = w.find('.sim-empty__text').text()
    expect(text.match(/\./g)).toHaveLength(2)
    expect(text).toContain('synthetische')
    expect(text).toContain('keine Vorhersage')
    expect(w.get('[data-testid="sim-empty-model"]').text()).toContain('std-model')
    expect(w.find('select, [role="combobox"]').exists()).toBe(false)
    expect((w.get('[data-testid="sim-empty-start"]').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('nennt ohne Standardmodell, dass keins erfasst ist', () => {
    h_.control.plannedModel.mockReturnValue(null)
    const w = mountIt()
    expect(w.get('[data-testid="sim-empty-model"]').text()).toContain('kein Standard erfasst')
  })

  it('sperrt den Start mit Begründung, solange die Personas nicht fertig sind', async () => {
    const w = mountIt({ personasReady: false })
    const btn = w.get('[data-testid="sim-empty-start"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)
    expect(btn.attributes('aria-describedby')).toBe('sim-empty-blocked')
    expect(w.get('#sim-empty-blocked').text()).toContain('Personas')
    await btn.trigger('click')
    expect(h_.control.start).not.toHaveBeenCalled()
  })

  it('startet über die Steuerung und meldet started mit der run_id', async () => {
    h_.control.start.mockResolvedValue({ runId: 'run_1' })
    const w = mountIt()
    await w.get('[data-testid="sim-empty-start"]').trigger('click')
    await flushPromises()
    expect(h_.control.start).toHaveBeenCalledTimes(1)
    expect(w.emitted('started')).toEqual([['run_1']])
  })

  it('zeigt einen Startfehler als role=alert', async () => {
    h_.control.start.mockImplementation(async () => {
      h_.control.error.value = 'Rate-Limit des Anbieters'
      return null
    })
    const w = mountIt()
    await w.get('[data-testid="sim-empty-start"]').trigger('click')
    await flushPromises()
    const alert = w.get('[data-testid="sim-empty-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('Rate-Limit des Anbieters')
    expect(w.emitted('started')).toBeUndefined()
  })
})
