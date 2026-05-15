import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarState } from '../useSidebarState'

const STORAGE_KEY = 'agora.sidebar.v1'

// localStorage-Mock (Bun-Testrunner hat kein jsdom built-in)
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

describe('useSidebarState', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('Default-State ist leere Map (alle Groups closed)', () => {
    const { isGroupOpen } = useSidebarState()
    expect(isGroupOpen('runs')).toBe(false)
    expect(isGroupOpen('settings')).toBe(false)
  })

  it('toggleGroup öffnet und schließt eine Group', () => {
    const { isGroupOpen, toggleGroup } = useSidebarState()
    toggleGroup('runs')
    expect(isGroupOpen('runs')).toBe(true)
    toggleGroup('runs')
    expect(isGroupOpen('runs')).toBe(false)
  })

  it('State persistiert in localStorage unter agora.sidebar.v1', () => {
    const { toggleGroup } = useSidebarState()
    toggleGroup('runs')
    const raw = localStorage.getItem(STORAGE_KEY)
    expect(raw).not.toBeNull()
    expect(JSON.parse(raw!).runs).toBe(true)
  })

  it('State wird aus localStorage hydratet', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ settings: true }))
    const { isGroupOpen } = useSidebarState()
    expect(isGroupOpen('settings')).toBe(true)
    expect(isGroupOpen('runs')).toBe(false)
  })

  it('setGroupOpen setzt explizit', () => {
    const { isGroupOpen, setGroupOpen } = useSidebarState()
    setGroupOpen('runs', true)
    expect(isGroupOpen('runs')).toBe(true)
    setGroupOpen('runs', false)
    expect(isGroupOpen('runs')).toBe(false)
  })

  it('korrupter localStorage wird graceful ignoriert', () => {
    localStorage.setItem(STORAGE_KEY, 'KEIN_JSON{{')
    expect(() => useSidebarState()).not.toThrow()
  })
})
