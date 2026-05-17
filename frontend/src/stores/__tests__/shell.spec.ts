/**
 * shell Store — mobileNavOpen Tests.
 *
 * Prueft:
 * 1. Default mobileNavOpen = false.
 * 2. openMobileNav setzt true.
 * 3. closeMobileNav setzt false.
 * 4. toggleMobileNav toggelt korrekt.
 * 5. mobileNavOpen wird NICHT in localStorage geschrieben.
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

describe('useShellStore — mobileNavOpen', () => {
  beforeEach(() => {
    localStorageMock.clear()
    setActivePinia(createPinia())
  })

  it('ist standardmaessig false', () => {
    const store = useShellStore()
    expect(store.mobileNavOpen).toBe(false)
  })

  it('openMobileNav setzt mobileNavOpen auf true', () => {
    const store = useShellStore()
    store.openMobileNav()
    expect(store.mobileNavOpen).toBe(true)
  })

  it('closeMobileNav setzt mobileNavOpen auf false', () => {
    const store = useShellStore()
    store.openMobileNav()
    store.closeMobileNav()
    expect(store.mobileNavOpen).toBe(false)
  })

  it('toggleMobileNav toggelt von false auf true', () => {
    const store = useShellStore()
    expect(store.mobileNavOpen).toBe(false)
    store.toggleMobileNav()
    expect(store.mobileNavOpen).toBe(true)
  })

  it('toggleMobileNav toggelt von true auf false', () => {
    const store = useShellStore()
    store.openMobileNav()
    store.toggleMobileNav()
    expect(store.mobileNavOpen).toBe(false)
  })

  it('mobileNavOpen wird NICHT in localStorage persistiert', async () => {
    const store = useShellStore()
    store.openMobileNav()
    await new Promise((r) => setTimeout(r, 0))
    // Kein localStorage-Key fuer mobileNavOpen erwartet
    expect(localStorageMock.getItem('agora.v4.shell.mobileNavOpen')).toBeNull()
  })
})
