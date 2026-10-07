import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'
import { useTheme } from '@/composables/useTheme'
import { useDensity } from '@/composables/useDensity'
import { useFontSize } from '@/composables/settings-window/useFontSize'
import SectionAppearance from '../../sections/SectionAppearance.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })
const html = () => document.documentElement

beforeEach(() => {
  localStorage.clear()
  html().removeAttribute('data-theme')
  html().removeAttribute('data-density')
  html().removeAttribute('data-font-size')
  useTheme._resetForTesting()
  useDensity._resetForTesting()
  useFontSize._resetForTesting()
})

function mountIt() {
  return mount(SectionAppearance, { attachTo: document.body, global: { plugins: [i18n] } })
}

describe('SectionAppearance', () => {
  it('rendert drei Radiogruppen mit Standardauswahl und ohne Platzhalter', () => {
    const w = mountIt()
    const groups = w.findAll('[role="radiogroup"]')
    expect(groups.map((g) => g.attributes('aria-label'))).toEqual(['Darstellung', 'Dichte', 'Schriftgröße'])
    const checked = w.findAll('[role="radio"][aria-checked="true"]').map((r) => r.text())
    expect(checked).toEqual(['System', 'Komfort', 'Normal'])
    expect(w.text()).not.toContain('In Vorbereitung')
    expect(w.find('h1').exists()).toBe(false)
    w.unmount()
  })

  it('Umschalten wirkt auf data-theme, data-density, data-font-size und Speicher', async () => {
    const w = mountIt()
    const radio = (label: string) => w.findAll('[role="radio"]').find((r) => r.text() === label)!

    await radio('Hell').trigger('click')
    expect(html().getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem('agora.theme')).toBe('light')

    await radio('Kompakt').trigger('click')
    expect(html().getAttribute('data-density')).toBe('compact')

    await radio('Groß').trigger('click')
    expect(html().getAttribute('data-font-size')).toBe('large')
    expect(localStorage.getItem('agora.fontSize')).toBe('large')
    expect(radio('Groß').attributes('aria-checked')).toBe('true')
    expect(radio('Normal').attributes('tabindex')).toBe('-1')
    w.unmount()
  })

  it('Pfeiltasten wechseln die Auswahl', async () => {
    const w = mountIt()
    const normal = w.findAll('[role="radio"]').find((r) => r.text() === 'Normal')!
    await normal.trigger('keydown', { key: 'ArrowRight' })
    expect(html().getAttribute('data-font-size')).toBe('large')
    w.unmount()
  })
})
