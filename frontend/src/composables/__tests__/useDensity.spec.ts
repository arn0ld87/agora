/**
 * useDensity — Tests für Compact/Comfortable-Density-Toggle.
 *
 * Slice FE-Redesign-6 · 2026-05-15
 *
 * Getestete Contracts:
 * 1. Default ist comfortable, wenn nichts in localStorage.
 * 2. Hydrate aus localStorage.
 * 3. Korrupter Wert fällt auf comfortable.
 * 4. setDensity aktualisiert localStorage + data-density-Attribut.
 * 5. applyOnMount setzt data-density aus aktuellem State.
 * 6. toggle wechselt comfortable<->compact.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useDensity } from '../useDensity'

const STORAGE_KEY = 'agora.density'

// ---------------------------------------------------------------------------
// LocalStorage-Stub (analog usePersonaQuota.spec.ts)
// ---------------------------------------------------------------------------

function makeLocalStorageStub(): Storage {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
    get length() { return Object.keys(store).length },
    key: (i: number) => Object.keys(store)[i] ?? null,
  }
}

let localStorageStub: Storage

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useDensity', () => {
  beforeEach(() => {
    localStorageStub = makeLocalStorageStub()
    vi.stubGlobal('localStorage', localStorageStub)
    document.documentElement.removeAttribute('data-density')
    // Reset module-level singleton für Test-Isolation
    useDensity._resetForTesting()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('Default ist comfortable, wenn nichts in localStorage', () => {
    const { density } = useDensity()
    expect(density.value).toBe('comfortable')
  })

  it('Hydrate aus localStorage', () => {
    localStorageStub.setItem(STORAGE_KEY, 'compact')
    useDensity._resetForTesting()
    const { density } = useDensity()
    expect(density.value).toBe('compact')
  })

  it('Korrupter Wert fällt auf comfortable', () => {
    localStorageStub.setItem(STORAGE_KEY, 'enormous')
    useDensity._resetForTesting()
    const { density } = useDensity()
    expect(density.value).toBe('comfortable')
  })

  it('setDensity aktualisiert localStorage + data-density-Attribut', () => {
    const { setDensity } = useDensity()
    setDensity('compact')
    expect(localStorageStub.getItem(STORAGE_KEY)).toBe('compact')
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
  })

  it('applyOnMount setzt data-density aus aktuellem State', () => {
    localStorageStub.setItem(STORAGE_KEY, 'compact')
    useDensity._resetForTesting()
    const { applyOnMount } = useDensity()
    applyOnMount()
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
  })

  it('toggle wechselt comfortable<->compact', () => {
    const { density, toggle } = useDensity()
    expect(density.value).toBe('comfortable')
    toggle()
    expect(density.value).toBe('compact')
    toggle()
    expect(density.value).toBe('comfortable')
  })
})
