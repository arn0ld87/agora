import { beforeEach, describe, expect, it } from 'vitest'
import { FONT_SIZE_STORAGE_KEY, useFontSize } from '../useFontSize'

describe('useFontSize', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-font-size')
    useFontSize._resetForTesting()
  })

  it('Standard ist normal', () => {
    expect(useFontSize().fontSize.value).toBe('normal')
  })

  it('liest gespeicherte Wahl und ignoriert ungültige Werte', () => {
    localStorage.setItem(FONT_SIZE_STORAGE_KEY, 'large')
    useFontSize._resetForTesting()
    expect(useFontSize().fontSize.value).toBe('large')
    localStorage.setItem(FONT_SIZE_STORAGE_KEY, 'huge')
    useFontSize._resetForTesting()
    expect(useFontSize().fontSize.value).toBe('normal')
  })

  it('setFontSize persistiert und setzt das Attribut; applyOnMount setzt es aus dem Zustand', () => {
    const f = useFontSize()
    f.setFontSize('small')
    expect(localStorage.getItem(FONT_SIZE_STORAGE_KEY)).toBe('small')
    expect(document.documentElement.getAttribute('data-font-size')).toBe('small')
    document.documentElement.removeAttribute('data-font-size')
    f.applyOnMount()
    expect(document.documentElement.getAttribute('data-font-size')).toBe('small')
  })
})
