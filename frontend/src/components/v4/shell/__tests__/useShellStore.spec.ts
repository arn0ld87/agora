/**
 * useShellStore — Vitest-Tests (Slice B, Design-v4).
 *
 * Prueft:
 * 1. Default-Werte (false / true / false).
 * 2. localStorage-Persistenz: Keys werden geschrieben.
 * 3. Alle Actions toggeln den erwarteten State.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// localStorage-Mock vor allen Imports
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => { delete store[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

import { useShellStore } from '@/stores/shell'

describe('useShellStore', () => {
  beforeEach(() => {
    localStorageMock.clear()
    setActivePinia(createPinia())
  })

  it('hat korrekte Default-Werte', () => {
    const store = useShellStore()
    expect(store.sidebarCollapsed).toBe(false)
    expect(store.settingsGroupOpen).toBe(true)
    expect(store.inspectorOpen).toBe(false)
  })

  it('toggleSidebar toggelt sidebarCollapsed', async () => {
    const store = useShellStore()
    expect(store.sidebarCollapsed).toBe(false)
    store.toggleSidebar()
    expect(store.sidebarCollapsed).toBe(true)
    store.toggleSidebar()
    expect(store.sidebarCollapsed).toBe(false)
  })

  it('toggleSettingsGroup toggelt settingsGroupOpen', () => {
    const store = useShellStore()
    expect(store.settingsGroupOpen).toBe(true)
    store.toggleSettingsGroup()
    expect(store.settingsGroupOpen).toBe(false)
  })

  it('openInspector / closeInspector setzen inspectorOpen korrekt', () => {
    const store = useShellStore()
    store.openInspector()
    expect(store.inspectorOpen).toBe(true)
    store.closeInspector()
    expect(store.inspectorOpen).toBe(false)
  })

  it('toggleInspector toggelt inspectorOpen', () => {
    const store = useShellStore()
    store.toggleInspector()
    expect(store.inspectorOpen).toBe(true)
    store.toggleInspector()
    expect(store.inspectorOpen).toBe(false)
  })

  it('schreibt sidebarCollapsed in localStorage (Key check)', async () => {
    const store = useShellStore()
    store.toggleSidebar()
    // Watch ist async (nextTick) — kurz warten
    await new Promise((r) => setTimeout(r, 0))
    expect(localStorageMock.getItem('agora.v4.shell.sidebarCollapsed')).toBe('true')
  })

  it('schreibt settingsGroupOpen in localStorage', async () => {
    const store = useShellStore()
    store.toggleSettingsGroup()
    await new Promise((r) => setTimeout(r, 0))
    expect(localStorageMock.getItem('agora.v4.shell.settingsGroupOpen')).toBe('false')
  })

  it('schreibt inspectorOpen in localStorage', async () => {
    const store = useShellStore()
    store.openInspector()
    await new Promise((r) => setTimeout(r, 0))
    expect(localStorageMock.getItem('agora.v4.shell.inspectorOpen')).toBe('true')
  })

  it('liest gespeicherten Wert beim naechsten Mount', () => {
    // Schreibe beforehand
    localStorageMock.setItem('agora.v4.shell.sidebarCollapsed', 'true')
    setActivePinia(createPinia())
    const store = useShellStore()
    expect(store.sidebarCollapsed).toBe(true)
  })
})
