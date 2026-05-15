/**
 * useCommandPalette — Unit-Tests
 *
 * 5 Tests:
 * 1. open() setzt isOpen=true + resettet query
 * 2. close() setzt isOpen=false
 * 3. toggle() wechselt den Zustand
 * 4. pushRecent: max 8 + Dedup
 * 5. localStorage-Persistenz: pushRecent schreibt, clearRecent loescht
 */
import { describe, it, expect, beforeEach } from 'vitest'

// localStorage-Mock (frisch pro Test)
const lsMock = (() => {
  const s: Record<string, string> = {}
  return {
    getItem: (k: string) => s[k] ?? null,
    setItem: (k: string, v: string) => {
      s[k] = v
    },
    removeItem: (k: string) => {
      delete s[k]
    },
    clear: () => {
      Object.keys(s).forEach((k) => {
        delete s[k]
      })
    },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: lsMock, writable: true })

// Import NACH Mock-Setup
import { useCommandPalette } from '../useCommandPalette'

describe('useCommandPalette', () => {
  beforeEach(() => {
    lsMock.clear()
    const { close, clearRecent, query } = useCommandPalette()
    close()
    clearRecent()
    query.value = ''
  })

  it('open() setzt isOpen=true und resettet query auf leeren String', () => {
    const { isOpen, query, open, close } = useCommandPalette()
    close()
    query.value = 'etwas'
    open()
    expect(isOpen.value).toBe(true)
    expect(query.value).toBe('')
  })

  it('close() setzt isOpen=false', () => {
    const { isOpen, open, close } = useCommandPalette()
    open()
    expect(isOpen.value).toBe(true)
    close()
    expect(isOpen.value).toBe(false)
  })

  it('toggle() wechselt von false auf true und zurueck', () => {
    const { isOpen, close, toggle } = useCommandPalette()
    close()
    toggle()
    expect(isOpen.value).toBe(true)
    toggle()
    expect(isOpen.value).toBe(false)
  })

  it('pushRecent: deduped + max 8 Eintraege', () => {
    const { recent, pushRecent, clearRecent } = useCommandPalette()
    clearRecent()

    // 10 IDs pushen
    for (let i = 0; i < 10; i++) {
      pushRecent(`cmd-${i}`)
    }
    expect(recent.value.length).toBe(8)

    // Duplikat — soll nach vorne ruecken, nicht verdoppeln
    pushRecent('cmd-9')
    expect(recent.value.length).toBe(8)
    expect(recent.value[0]).toBe('cmd-9')
  })

  it('localStorage-Persistenz: pushRecent schreibt, clearRecent loescht', () => {
    const { pushRecent, clearRecent } = useCommandPalette()
    clearRecent()

    pushRecent('nav:dashboard')
    const stored = lsMock.getItem('agora.cmdk.recent')
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored as string) as string[]
    expect(parsed).toContain('nav:dashboard')

    clearRecent()
    expect(lsMock.getItem('agora.cmdk.recent')).toBeNull()
  })
})
