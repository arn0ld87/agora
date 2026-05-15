/**
 * commandsStore — Unit-Tests
 *
 * 4 Tests:
 * 1. buildStaticCommands liefert alle Top-Level-Nav-Routes als Commands
 * 2. filter() filtert korrekt nach Query
 * 3. getOrdered(): Recent-Commands erscheinen zuerst
 * 4. getOrdered() ohne Recent liefert unveraenderte Reihenfolge
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// localStorage-Mock
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

import { useCommandsStore } from '../commandsStore'
import { useCommandPalette } from '@/composables/useCommandPalette'

// Router-Mock: router.push ist ein vi.fn()
const routerMock = {
  push: vi.fn().mockResolvedValue(undefined),
}

describe('commandsStore', () => {
  beforeEach(() => {
    lsMock.clear()
    setActivePinia(createPinia())
    const { clearRecent } = useCommandPalette()
    clearRecent()
    routerMock.push.mockClear()
  })

  it('buildStaticCommands liefert alle Nav-Top-Level-Routes', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    // Mindestens: Dashboard, Runs, History + Settings-Unterseiten
    const ids = cmds.map((c) => c.id)
    expect(ids).toContain('nav:dashboard')
    expect(ids).toContain('nav:runs')
    expect(ids).toContain('nav:history')
    expect(ids).toContain('nav:settings-general')
    expect(ids).toContain('nav:settings-llm-routing')
    expect(cmds.length).toBeGreaterThanOrEqual(5)
  })

  it('filter() gibt alle Commands zurueck wenn query leer', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    const result = store.filter(cmds, '')
    expect(result.length).toBe(cmds.length)
  })

  it('filter() filtert korrekt nach Query-String', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    const result = store.filter(cmds, 'dashboard')
    expect(result.length).toBeGreaterThanOrEqual(1)
    expect(result.every((c) => c.label.toLowerCase().includes('dashboard') || c.id.includes('dashboard'))).toBe(true)

    const noResult = store.filter(cmds, 'xyznotexistent123')
    expect(noResult.length).toBe(0)
  })

  it('getOrdered() schiebt Recent-Commands an den Anfang', () => {
    const store = useCommandsStore()
    const { pushRecent } = useCommandPalette()
    const cmds = store.buildStaticCommands(routerMock as never)

    // 'nav:runs' als Recent setzen
    pushRecent('nav:runs')
    const ordered = store.getOrdered(cmds)

    expect(ordered[0].id).toBe('nav:runs')
    // group ist 'recent' fuer priorisierte Commands
    expect(ordered[0].group).toBe('recent')
    // Restliche Commands folgen
    expect(ordered.length).toBe(cmds.length)
  })

  it('getOrdered() ohne Recent liefert unveraenderte Reihenfolge', () => {
    const store = useCommandsStore()
    const cmds = store.buildStaticCommands(routerMock as never)
    const ordered = store.getOrdered(cmds)
    expect(ordered.map((c) => c.id)).toEqual(cmds.map((c) => c.id))
  })
})
