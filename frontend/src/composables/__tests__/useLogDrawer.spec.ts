/**
 * useLogDrawer — Unit-Tests
 *
 * 4 Tests:
 * 1. open() setzt isOpen=true
 * 2. close() setzt isOpen=false
 * 3. toggle() wechselt den Zustand
 * 4. handleHotkey: Ctrl+Shift+L (und Cmd+Shift+L) togglen, andere Kombis nicht
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
import { useLogDrawer } from '../useLogDrawer'

function makeKeyEvent(overrides: Partial<KeyboardEventInit> = {}): KeyboardEvent {
  return new KeyboardEvent('keydown', {
    key: 'L',
    ctrlKey: true,
    shiftKey: true,
    cancelable: true,
    ...overrides,
  })
}

describe('useLogDrawer', () => {
  beforeEach(() => {
    lsMock.clear()
    const { close } = useLogDrawer()
    close()
  })

  it('open() setzt isOpen=true', () => {
    const { isOpen, open, close } = useLogDrawer()
    close()
    open()
    expect(isOpen.value).toBe(true)
  })

  it('close() setzt isOpen=false', () => {
    const { isOpen, open, close } = useLogDrawer()
    open()
    expect(isOpen.value).toBe(true)
    close()
    expect(isOpen.value).toBe(false)
  })

  it('toggle() wechselt von false auf true und zurueck', () => {
    const { isOpen, close, toggle } = useLogDrawer()
    close()
    toggle()
    expect(isOpen.value).toBe(true)
    toggle()
    expect(isOpen.value).toBe(false)
  })

  it('handleHotkey: Ctrl+Shift+L togglet den Drawer und unterdrueckt das Default-Verhalten', () => {
    const { isOpen, close, handleHotkey } = useLogDrawer()
    close()
    const event = makeKeyEvent()
    handleHotkey(event)
    expect(isOpen.value).toBe(true)
    expect(event.defaultPrevented).toBe(true)
  })

  it('handleHotkey: Cmd+Shift+L (metaKey) togglet ebenfalls', () => {
    const { isOpen, close, handleHotkey } = useLogDrawer()
    close()
    handleHotkey(makeKeyEvent({ ctrlKey: false, metaKey: true }))
    expect(isOpen.value).toBe(true)
  })

  it('handleHotkey: andere Tastenkombinationen loesen nichts aus', () => {
    const { isOpen, close, handleHotkey } = useLogDrawer()
    close()
    handleHotkey(makeKeyEvent({ key: 'L', ctrlKey: true, shiftKey: false }))
    expect(isOpen.value).toBe(false)
    handleHotkey(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(isOpen.value).toBe(false)
  })

  it('persistiert den Zustand in localStorage', () => {
    const { open, close } = useLogDrawer()
    close()
    open()
    expect(lsMock.getItem('agora.ui.logDrawer.open')).toBe('true')
    close()
    expect(lsMock.getItem('agora.ui.logDrawer.open')).toBe('false')
  })
})
