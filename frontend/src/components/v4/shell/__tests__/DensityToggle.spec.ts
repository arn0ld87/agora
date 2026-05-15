/**
 * DensityToggle — Smoke-Tests (Slice FE-Redesign-6).
 *
 * Getestete Contracts:
 * 1. Rendert Comfort-Label im Default (aria-pressed=false).
 * 2. Klick toggled auf compact: Label, aria-pressed, DOM-Attribut, localStorage.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DensityToggle from '../DensityToggle.vue'
import { useDensity } from '@/composables/useDensity'

// ---------------------------------------------------------------------------
// LocalStorage-Stub
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DensityToggle', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', makeLocalStorageStub())
    document.documentElement.removeAttribute('data-density')
    useDensity._resetForTesting()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('rendert Comfort-Label im Default', () => {
    const wrapper = mount(DensityToggle)
    expect(wrapper.text()).toContain('Komfort')
    expect(wrapper.find('button').attributes('aria-pressed')).toBe('false')
  })

  it('Klick toggled auf compact und setzt aria-pressed=true', async () => {
    const wrapper = mount(DensityToggle)
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('Kompakt')
    expect(wrapper.find('button').attributes('aria-pressed')).toBe('true')
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
    expect(localStorage.getItem('agora.density')).toBe('compact')
  })
})
