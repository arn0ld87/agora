/**
 * useShellVariant — Unit-Tests (Block B3, PLAN.md Abschnitt 2).
 *
 * Das Modul cached seinen Ref auf Modulebene (`const variant = ref(...)`,
 * einmal beim Import ausgewertet) — deshalb hier vi.resetModules() +
 * dynamischer import() je Testfall, statt eines statischen Top-Level-Imports.
 *
 * 5 Tests:
 * 1. localStorage['agora.shell']='dossier' -> dossier
 * 2. ungueltiger localStorage-Wert -> Fallback auf dossier (kein env gesetzt)
 * 3. ungueltiger localStorage-Wert + VITE_AGORA_SHELL='dossier' -> Fallback auf env
 * 4. setVariant schreibt localStorage und aktualisiert das Ref
 * 5. localStorage wirft (Object.defineProperty-Mock) -> kein Crash, Default dossier
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

function installLocalStorageMock(initial: Record<string, string> = {}) {
  const store: Record<string, string> = { ...initial }
  const mock = {
    getItem: vi.fn((k: string) => store[k] ?? null),
    setItem: vi.fn((k: string, v: string) => {
      store[k] = v
    }),
    removeItem: vi.fn((k: string) => {
      delete store[k]
    }),
  }
  Object.defineProperty(globalThis, 'localStorage', { value: mock, writable: true, configurable: true })
  return { mock, store }
}

describe('useShellVariant', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("localStorage['agora.shell']='dossier' fuehrt zu variant='dossier'", async () => {
    installLocalStorageMock({ 'agora.shell': 'dossier' })

    const { useShellVariant } = await import('../useShellVariant')
    const { variant } = useShellVariant()

    expect(variant.value).toBe('dossier')
  })

  it('ein ungueltiger localStorage-Wert faellt auf dossier zurueck (kein Build-Default gesetzt)', async () => {
    installLocalStorageMock({ 'agora.shell': 'not-a-real-variant' })
    vi.stubEnv('VITE_AGORA_SHELL', '')

    const { useShellVariant } = await import('../useShellVariant')
    const { variant } = useShellVariant()

    expect(variant.value).toBe('dossier')
  })

  it('ein ungueltiger localStorage-Wert faellt auf den Build-Default VITE_AGORA_SHELL zurueck', async () => {
    installLocalStorageMock({ 'agora.shell': 'not-a-real-variant' })
    vi.stubEnv('VITE_AGORA_SHELL', 'dossier')

    const { useShellVariant } = await import('../useShellVariant')
    const { variant } = useShellVariant()

    expect(variant.value).toBe('dossier')
  })

  it('setVariant schreibt localStorage und aktualisiert das Ref', async () => {
    const { store } = installLocalStorageMock()

    const { useShellVariant } = await import('../useShellVariant')
    const { variant, setVariant } = useShellVariant()

    expect(variant.value).toBe('dossier')
    setVariant('dossier')

    expect(variant.value).toBe('dossier')
    expect(store['agora.shell']).toBe('dossier')
  })

  it('localStorage wirft (z.B. Privacy-Mode) -> kein Crash, Default bleibt dossier', async () => {
    Object.defineProperty(globalThis, 'localStorage', {
      get() {
        throw new Error('SecurityError: localStorage ist blockiert')
      },
      configurable: true,
    })

    const { useShellVariant } = await import('../useShellVariant')
    const { variant, setVariant } = useShellVariant()

    expect(variant.value).toBe('dossier')
    expect(() => setVariant('dossier')).not.toThrow()
    // setVariant aktualisiert das Ref trotzdem — nur die Persistenz schlaegt fehl.
    expect(variant.value).toBe('dossier')
  })
})
