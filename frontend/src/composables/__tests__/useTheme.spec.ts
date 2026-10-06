import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEME_STORAGE_KEY, useTheme } from '../useTheme'

// Steuerbares matchMedia: `emit(true)` simuliert den Wechsel des Systems auf Dunkel.
function installMatchMedia(initialDark: boolean) {
  let dark = initialDark
  const listeners = new Set<(e: MediaQueryListEvent) => void>()
  const mql = {
    get matches() {
      return dark
    },
    media: '(prefers-color-scheme: dark)',
    addEventListener: (_t: string, l: (e: MediaQueryListEvent) => void) => listeners.add(l),
    removeEventListener: (_t: string, l: (e: MediaQueryListEvent) => void) => listeners.delete(l),
  }
  window.matchMedia = vi.fn(() => mql as unknown as MediaQueryList)
  return {
    listenerCount: () => listeners.size,
    emit(nextDark: boolean) {
      dark = nextDark
      for (const l of [...listeners]) l({ matches: nextDark } as MediaQueryListEvent)
    },
  }
}

const html = () => document.documentElement

describe('useTheme', () => {
  const originalMatchMedia = window.matchMedia

  beforeEach(() => {
    useTheme._resetForTesting()
    localStorage.clear()
    html().removeAttribute('data-theme')
    html().style.colorScheme = ''
  })

  afterEach(() => {
    useTheme._resetForTesting()
    window.matchMedia = originalMatchMedia
    vi.restoreAllMocks()
  })

  it('Standard ohne gespeicherte Wahl: system, folgt dem System (dunkel)', () => {
    installMatchMedia(true)
    const t = useTheme()
    expect(t.choice.value).toBe('system')
    expect(t.resolved.value).toBe('dark')
    expect(html().getAttribute('data-theme')).toBe('dark')
    expect(html().style.colorScheme).toBe('dark')
  })

  it('Standard ohne gespeicherte Wahl: system, folgt dem System (hell)', () => {
    installMatchMedia(false)
    const t = useTheme()
    expect(t.choice.value).toBe('system')
    expect(t.resolved.value).toBe('light')
    expect(html().getAttribute('data-theme')).toBe('light')
    expect(html().style.colorScheme).toBe('light')
  })

  it('gespeicherte Wahl gewinnt gegen das System und überlebt das Neuladen', () => {
    installMatchMedia(true)
    useTheme().setChoice('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(html().getAttribute('data-theme')).toBe('light')

    // „Neuladen“: Singleton verwerfen, Speicher bleibt.
    useTheme._resetForTesting()
    html().removeAttribute('data-theme')
    const reloaded = useTheme()
    expect(reloaded.choice.value).toBe('light')
    expect(reloaded.resolved.value).toBe('light')
    expect(html().getAttribute('data-theme')).toBe('light')
  })

  it('ungültiger gespeicherter Wert fällt auf system zurück', () => {
    installMatchMedia(false)
    localStorage.setItem(THEME_STORAGE_KEY, 'sepia')
    expect(useTheme().choice.value).toBe('system')
  })

  it('Systemwechsel zur Laufzeit wird mit Wahl system übernommen', () => {
    const mm = installMatchMedia(true)
    const t = useTheme()
    expect(t.resolved.value).toBe('dark')
    mm.emit(false)
    expect(t.resolved.value).toBe('light')
    expect(html().getAttribute('data-theme')).toBe('light')
    expect(html().style.colorScheme).toBe('light')
    mm.emit(true)
    expect(html().getAttribute('data-theme')).toBe('dark')
  })

  it('Systemwechsel ändert eine gespeicherte Wahl nicht', () => {
    const mm = installMatchMedia(true)
    const t = useTheme()
    t.setChoice('dark')
    mm.emit(false)
    expect(t.resolved.value).toBe('dark')
    expect(html().getAttribute('data-theme')).toBe('dark')
  })

  it('zurück auf system folgt wieder dem System', () => {
    installMatchMedia(false)
    const t = useTheme()
    t.setChoice('dark')
    expect(t.resolved.value).toBe('dark')
    t.setChoice('system')
    expect(t.resolved.value).toBe('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')
  })

  it('gesperrter localStorage bricht nichts', () => {
    installMatchMedia(false)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('gesperrt')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('gesperrt')
    })
    const t = useTheme()
    expect(t.choice.value).toBe('system')
    expect(() => t.setChoice('dark')).not.toThrow()
    expect(t.resolved.value).toBe('dark')
  })

  it('ist ein Singleton und räumt den Listener beim Zurücksetzen auf', () => {
    const mm = installMatchMedia(true)
    const a = useTheme()
    const b = useTheme()
    a.setChoice('light')
    expect(b.choice.value).toBe('light')
    expect(mm.listenerCount()).toBe(1)
    useTheme._resetForTesting()
    expect(mm.listenerCount()).toBe(0)
  })

  it('ohne matchMedia: system löst auf dunkel auf', () => {
    // @ts-expect-error Umgebung ohne matchMedia simulieren
    window.matchMedia = undefined
    expect(useTheme().resolved.value).toBe('dark')
  })
})
