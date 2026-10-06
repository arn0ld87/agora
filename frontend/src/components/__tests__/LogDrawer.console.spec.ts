/**
 * LogDrawer als Konsole (#1795, Ticket 8): Höhen-Griff per Tastatur,
 * zusammengefasste Fortschrittsbalken, Beschriftungen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const store: Record<string, string> = {}
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  },
  writable: true,
})

vi.mock('../../api/logs', () => ({
  fetchLogs: vi.fn().mockResolvedValue({
    data: {
      success: true,
      data: {
        lines: [
          'INFO start',
          'twhin-bert:   0%|    | 0/4\rtwhin-bert:  50%|██  | 2/4\rtwhin-bert: 100%|████| 4/4\r',
          'ERROR kaputt',
        ],
        offset: 0,
      },
    },
  }),
  buildLogsStreamUrl: vi.fn().mockResolvedValue('http://localhost/api/logs/stream'),
}))
vi.mock('../../composables/useStickyScroll', () => ({
  useStickyScroll: vi.fn().mockReturnValue({
    unreadCount: { value: 0 },
    scrollToBottom: vi.fn(),
    markAppended: vi.fn(),
  }),
}))
class NoopEventSource {
  onmessage = null
  onerror = null
  close = vi.fn()
}
// @ts-expect-error – globales EventSource durch Mock ersetzen
globalThis.EventSource = NoopEventSource

import LogDrawer from '../LogDrawer.vue'
import { useLogDrawerHeight } from '../../composables/useLogDrawer'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      logs: { drawer: { title: 'Backend-Logs', resize: 'Höhe ändern', levelFilter: 'Stufe filtern', search: 'Suchen…', pause: 'Pause', empty: 'leer', copy: 'Kopieren', copyTitle: 'Sichtbare Zeilen kopieren', copied: 'Kopiert', copyFailed: 'Kopieren fehlgeschlagen' } },
      common: { close: 'Schließen' },
    },
  },
})
const global = { plugins: [i18n], stubs: { StickyScrollBanner: { template: '<div />' } } }

describe('LogDrawer als Konsole', () => {
  beforeEach(() => {
    useLogDrawerHeight().setHeight(320)
  })

  it('fasst Fortschrittsbalken zu einer Zeile mit dem letzten Stand zusammen', async () => {
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    const rows = w.findAll('.log-line').map((r) => r.text())
    expect(rows).toEqual(['INFO start', 'twhin-bert: 100%|████| 4/4', 'ERROR kaputt'])
    expect(w.findAll('.log-line.is-error')).toHaveLength(1)
    w.unmount()
  })

  it('Griff: Rolle, Beschriftung und Höhe per Pfeiltasten, Home/Ende', async () => {
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    const handle = w.get('[role="separator"]')
    expect(handle.attributes('aria-label')).toBe('Höhe ändern')
    expect(handle.attributes('tabindex')).toBe('0')
    expect(handle.attributes('aria-valuenow')).toBe('320')

    await handle.trigger('keydown', { key: 'ArrowUp' })
    expect(handle.attributes('aria-valuenow')).toBe('344')
    await handle.trigger('keydown', { key: 'ArrowDown', shiftKey: true })
    expect(handle.attributes('aria-valuenow')).toBe('248')
    await handle.trigger('keydown', { key: 'End' })
    expect(handle.attributes('aria-valuenow')).toBe('160')
    expect((w.get('.log-drawer').element as HTMLElement).style.height).toBe('160px')
    expect(store['agora.ui.logDrawer.height']).toBe('160')
    w.unmount()
  })

  it('Griff: Ziehen mit dem Zeiger verändert die Höhe', async () => {
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    w.get('[role="separator"]').element.dispatchEvent(new MouseEvent('pointerdown', { clientY: 500, bubbles: true, cancelable: true }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientY: 450 }))
    await flushPromises()
    expect(w.get('[role="separator"]').attributes('aria-valuenow')).toBe('370')
    window.dispatchEvent(new MouseEvent('pointerup'))
    w.unmount()
  })

  it('Kopieren: schreibt genau die sichtbaren Zeilen, Rückmeldung per Statusregion', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    await w.get('.search-input').setValue('twhin')
    await w.get('.copy-btn').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('twhin-bert: 100%|████| 4/4')
    expect(w.get('[role="status"]').text()).toBe('Kopiert')
    await w.get('.search-input').setValue('')
    await w.get('.copy-btn').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenLastCalledWith('INFO start\ntwhin-bert: 100%|████| 4/4\nERROR kaputt')
    w.unmount()
  })

  it('Kopieren: Fehler wird sichtbar gemeldet', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    await w.get('.copy-btn').trigger('click')
    await flushPromises()
    expect(w.get('[role="status"]').text()).toBe('Kopieren fehlgeschlagen')
    expect(w.get('[role="status"]').classes()).toContain('is-error')
    w.unmount()
  })

  it('Kopieren: deaktiviert, wenn keine Zeile sichtbar ist', async () => {
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    expect(w.get('.copy-btn').attributes('disabled')).toBeUndefined()
    await w.get('.search-input').setValue('gibt-es-nicht')
    expect(w.get('.copy-btn').attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('Schließen-Knopf ist beschriftet und löst close aus', async () => {
    const w = mount(LogDrawer, { props: { open: true }, global })
    await flushPromises()
    const btn = w.get('button.close-btn')
    expect(btn.attributes('aria-label')).toBe('Schließen')
    await btn.trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })
})
