/**
 * ShellRoot — Komponenten-Tests (Block B3).
 *
 * Prueft:
 * 1. Mountet ohne Crash und rendert die Slot-Inhalte (shelf/dossier).
 * 2. Strg/Cmd+K oeffnet die (lazy gemountete) Command-Palette.
 * 3. Der Stapel-Zurueck-Knopf emittiert select(null).
 * 4. Abbrechen aus dem Aktivitaets-Indikator zeigt den globalen Undo-Toast.
 * 5. Der Undo-Knopf im Toast bricht den Abbruch ab, ohne die API zu rufen.
 *
 * Selektoren ausschliesslich ueber ShellTestId (src/contracts/testIds.ts).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
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

import { cancelRun } from '../../../api/runs'
import { useCancelAction } from '../useCancelAction'
import { useCommandPalette } from '../../../composables/useCommandPalette'
import ShellRoot from '../ShellRoot.vue'

// localStorage-Mock — useCommandPalette (via ShellRoot) liest/schreibt "recent".
const lsMock = (() => {
  const s: Record<string, string> = {}
  return {
    getItem: (k: string) => s[k] ?? null,
    setItem: (k: string, v: string) => { s[k] = v },
    removeItem: (k: string) => { delete s[k] },
    clear: () => { Object.keys(s).forEach((k) => { delete s[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: lsMock, writable: true })

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

const commandPaletteStub = { template: '<div data-testid="command-palette-stub" />' }

function makeObject(overrides: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf',
    id: 'sim_1',
    title: 'Testlauf',
    statusLine: 'Laeuft',
    updatedAt: '2026-08-18T10:00:00Z',
    metaId: 'sim_1',
    nextAction: null,
    active: { runId: 'run_1', status: 'processing', pausable: true, simulationId: 'sim_1' },
    ...overrides,
  }
}

function mountShell(props: { current?: ShelfObject | null; activeObjects?: ShelfObject[] } = {}) {
  return mount(ShellRoot, {
    props: { current: props.current ?? null, activeObjects: props.activeObjects ?? [] },
    slots: {
      shelf: '<div data-testid="shelf-slot-marker">shelf-inhalt</div>',
      dossier: '<div data-testid="dossier-slot-marker">dossier-inhalt</div>',
    },
    global: {
      plugins: [i18n, createPinia()],
      stubs: { CommandPalette: commandPaletteStub },
    },
  })
}

describe('ShellRoot', () => {
  beforeEach(() => {
    lsMock.clear()
    useCancelAction().undo()
    useCommandPalette().close()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('mountet ohne Crash und rendert die Slot-Inhalte', () => {
    const wrapper = mountShell()
    expect(wrapper.find(`[data-testid="${ShellTestId.root}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-testid="shelf-slot-marker"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="dossier-slot-marker"]').exists()).toBe(true)
  })

  it('Strg+K oeffnet die Command-Palette (erst nach dem ersten Oeffnen gemountet)', async () => {
    const wrapper = mountShell()
    expect(wrapper.find('[data-testid="command-palette-stub"]').exists()).toBe(false)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()

    expect(wrapper.find('[data-testid="command-palette-stub"]').exists()).toBe(true)
  })

  it('der Stapel-Zurueck-Knopf emittiert select(null)', async () => {
    const wrapper = mountShell({ current: makeObject() })
    await wrapper.find(`[data-testid="${ShellTestId.stackBack}"]`).trigger('click')

    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual([null])
  })

  it('Abbrechen aus dem Aktivitaets-Indikator zeigt den globalen Undo-Toast', async () => {
    const obj = makeObject()
    const wrapper = mountShell({ activeObjects: [obj] })

    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(false)

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    await wrapper.find(`[data-testid="${ShellTestId.activityCancel}"]`).trigger('click')

    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(true)
  })

  it('der Undo-Knopf im Toast bricht den Abbruch ab, ohne cancelRun aufzurufen', async () => {
    vi.useFakeTimers()
    const obj = makeObject()
    const wrapper = mountShell({ activeObjects: [obj] })

    await wrapper.find(`[data-testid="${ShellTestId.activityIndicator}"]`).trigger('click')
    await wrapper.find(`[data-testid="${ShellTestId.activityCancel}"]`).trigger('click')
    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(true)

    await wrapper.find(`[data-testid="${ShellTestId.undoButton}"]`).trigger('click')
    await nextTick()

    expect(wrapper.find(`[data-testid="${ShellTestId.undoToast}"]`).exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(6000)
    expect(cancelRun).not.toHaveBeenCalled()
  })
})
