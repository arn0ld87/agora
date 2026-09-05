/**
 * ActivityIndicator — Komponenten-Tests (Block B3).
 *
 * Prueft:
 * 1. Kein Rendering ohne aktive Objekte (Trigger nicht vorhanden).
 * 2. Trigger zeigt die Anzahl laufender Objekte.
 * 3. Klick auf den Trigger oeffnet/schliesst das Panel (aria-expanded).
 * 4. Escape schliesst das geoeffnete Panel.
 * 5. Abbrechen-Knopf ist deaktiviert ohne active, aktiv mit active.
 * 6. Abbrechen ruft useCancelAction.cancel() mit der richtigen runId auf.
 *
 * Der Klick auf ein einzelnes Aktivitaets-Element (das select-Event) traegt
 * keine eigene data-testid und wird deshalb bewusst NICHT getestet (siehe
 * Abschlussbericht) — nur ShellTestId.activityIndicator/activityCancel existieren.
 *
 * Selektoren ausschliesslich ueber ShellTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { ShellTestId } from '../../../contracts/testIds'
import type { ShelfObject } from '../../../types/shelf'

vi.mock('../../../api/runs', () => ({
  cancelRun: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/simulation', () => ({
  pauseSimulation: vi.fn().mockResolvedValue({}),
  resumeSimulation: vi.fn().mockResolvedValue({}),
}))

import { useCancelAction } from '../useCancelAction'
import ActivityIndicator from '../ActivityIndicator.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf eins',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: null,
    ...overrides,
  }
}

function mountIndicator(objects: ShelfObject[]) {
  return mount(ActivityIndicator, {
    props: { objects },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
}

describe('ActivityIndicator', () => {
  beforeEach(() => {
    useCancelAction().undo()
  })

  it('rendert nichts ohne aktive Objekte', () => {
    const wrapper = mountIndicator([])
    expect(wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).exists()).toBe(false)
  })

  it('der Trigger zeigt die Anzahl laufender Objekte', () => {
    const wrapper = mountIndicator([makeObject({ id: 'a' }), makeObject({ id: 'b' })])
    expect(wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).text()).toContain('2')
  })

  it('Klick auf den Trigger oeffnet das Panel, Escape schliesst es wieder', async () => {
    const wrapper = mountIndicator([makeObject()])
    const trigger = wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`)
    expect(trigger.attributes('aria-expanded')).toBe('false')

    await trigger.trigger('click')
    expect(wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).attributes('aria-expanded')).toBe('true')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).attributes('aria-expanded')).toBe('false')

    wrapper.unmount()
  })

  it('Abbrechen-Knopf ist deaktiviert ohne active und aktiv mit active', async () => {
    const withActive = makeObject({ active: { runId: 'run_a', status: 'processing', pausable: false, simulationId: null, progress: null } })
    const withoutActive = makeObject({ id: 'b', active: null })
    const wrapper = mountIndicator([withActive, withoutActive])

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    const cancelButtons = wrapper.findAll(`[data-testid="${ShellTestId.activityCancel}"]`)
    expect(cancelButtons[0].attributes('disabled')).toBeUndefined()
    expect(cancelButtons[1].attributes('disabled')).toBeDefined()

    wrapper.unmount()
  })

  it('Abbrechen ruft useCancelAction.cancel() mit der richtigen runId auf', async () => {
    const obj = makeObject({ active: { runId: 'run_xyz', status: 'processing', pausable: false, simulationId: null, progress: null } })
    const wrapper = mountIndicator([obj])
    const cancelAction = useCancelAction()

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    await wrapper.find(`[data-testid="${ShellTestId.activityCancel}"]`).trigger('click')

    expect(cancelAction.pending.value?.runId).toBe('run_xyz')

    wrapper.unmount()
  })
})
