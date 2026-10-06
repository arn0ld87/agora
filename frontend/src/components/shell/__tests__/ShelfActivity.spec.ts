/**
 * ShelfActivity + UndoToast — Aktivitaets-Indikator in der Kopfleiste der
 * einen Huelle (#1795, Ticket 5; ex ShellRoot-Spec, Block B3).
 *
 * Prueft:
 * 1. Ohne laufende Objekte im Shell-Store erscheint kein Indikator.
 * 2. Abbrechen aus dem Indikator zeigt den globalen Undo-Toast.
 * 3. Der Undo-Knopf im Toast bricht den Abbruch ab, ohne die API zu rufen.
 * 4. Ein Klick auf einen Eintrag oeffnet ihn in der Ablage (ShelfObject-Route).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { ShellTestId } from '../../../contracts/testIds'
import { useShellStore } from '@/stores/shell'
import type { ShelfObject } from '../../../types/shelf'

vi.mock('../../../api/runs', () => ({
  cancelRun: vi.fn().mockResolvedValue({ success: true }),
}))
vi.mock('../../../api/simulation', () => ({
  pauseSimulation: vi.fn().mockResolvedValue({}),
  resumeSimulation: vi.fn().mockResolvedValue({}),
}))

import { cancelRun } from '../../../api/runs'
import { useCancelAction } from '../useCancelAction'
import ShelfActivity from '../ShelfActivity.vue'
import UndoToast from '../UndoToast.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
const stubView = { template: '<div />' }

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: { runId: 'run_1', status: 'processing', pausable: true, simulationId: 'sim_1', progress: null },
    ...overrides,
  }
}

function mountHost(activeObjects: ShelfObject[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useShellStore().activeObjects = activeObjects
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ablage/:kind/:objectId', name: 'ShelfObject', component: stubView },
      { path: '/', name: 'Home', component: stubView },
    ],
  })
  const Host = defineComponent({
    setup: () => () => h('div', [h(ShelfActivity), h(UndoToast)]),
  })
  const wrapper = mount(Host, { global: { plugins: [i18n, pinia, router] } })
  return { wrapper, router }
}

describe('ShelfActivity', () => {
  beforeEach(() => {
    useCancelAction().undo()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('zeigt ohne laufende Objekte keinen Indikator', () => {
    const { wrapper } = mountHost([])
    expect(wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).exists()).toBe(false)
  })

  it('Abbrechen aus dem Aktivitaets-Indikator zeigt den globalen Undo-Toast', async () => {
    const { wrapper } = mountHost([makeObject()])

    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(false)

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    await wrapper.find(`[data-testid="${ShellTestId.activityCancel}"]`).trigger('click')

    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(true)
  })

  it('der Undo-Knopf im Toast bricht den Abbruch ab, ohne cancelRun aufzurufen', async () => {
    vi.useFakeTimers()
    const { wrapper } = mountHost([makeObject()])

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    await wrapper.find(`[data-testid="${ShellTestId.activityCancel}"]`).trigger('click')
    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(true)

    await wrapper.find(`[data-testid="${ShellTestId.undoButton}"]`).trigger('click')
    await nextTick()

    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(6000)
    expect(cancelRun).not.toHaveBeenCalled()
  })

  it('ein Klick auf einen Eintrag oeffnet ihn in der Ablage', async () => {
    const { wrapper, router } = mountHost([makeObject()])

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    await wrapper.find('.activity__item-label').trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.fullPath).toBe('/ablage/lauf/sim_1')
    })
  })
})
