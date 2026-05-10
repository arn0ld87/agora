/**
 * ReportModeControls — Unit Tests (P4.1 Frontend-Teil)
 *
 * Prueft:
 * - Alle drei Report-Modus-Optionen werden gerendert.
 * - Default-Wert ist "balanced".
 * - v-model emit bei Auswahl.
 * - i18n-Keys vorhanden.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportModeControls from '../ReportModeControls.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      reportMode: {
        label: 'Report-Modus',
        strict: {
          label: 'Strikt',
          hint: 'Nur belegte Claims. Keine Hypothesen. Harter Anchor-Validator.',
        },
        balanced: {
          label: 'Ausgewogen (Standard)',
          hint: 'Belegte Claims plus markierte Hypothesen. (Standard)',
        },
        explorative: {
          label: 'Explorativ',
          hint: 'Alle Claims, EXPLORATIVE-Banner. Brainstorming-/Discovery-Modus.',
        },
      },
    },
  },
})

const globalConfig = {
  plugins: [i18n],
  // Select.vue ist eine echte Komponente — nicht stubben, damit options gerendert werden.
}

describe('ReportModeControls', () => {
  it('rendert alle drei Modus-Optionen im select', () => {
    const wrapper = mount(ReportModeControls, {
      props: { modelValue: 'balanced' },
      global: globalConfig,
    })
    const options = wrapper.findAll('option')
    const values = options.map((o) => o.element.value)
    expect(values).toContain('strict')
    expect(values).toContain('balanced')
    expect(values).toContain('explorative')
  })

  it('default modelValue ist "balanced" wenn kein Prop übergeben', () => {
    const wrapper = mount(ReportModeControls, {
      global: globalConfig,
    })
    const select = wrapper.find('select')
    expect(select.element.value).toBe('balanced')
  })

  it('emittiert update:modelValue beim Ändern des select', async () => {
    const wrapper = mount(ReportModeControls, {
      props: { modelValue: 'balanced' },
      global: globalConfig,
    })
    const select = wrapper.find('select')
    await select.setValue('strict')
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted![0]).toEqual(['strict'])
  })

  it('emittiert "explorative" korrekt', async () => {
    const wrapper = mount(ReportModeControls, {
      props: { modelValue: 'balanced' },
      global: globalConfig,
    })
    const select = wrapper.find('select')
    await select.setValue('explorative')
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted![0]).toEqual(['explorative'])
  })

  it('rendert i18n-Label fuer Report-Modus', () => {
    const wrapper = mount(ReportModeControls, {
      props: { modelValue: 'balanced' },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('Report-Modus')
  })

  it('zeigt Hint-Text fuer den aktiven Modus', () => {
    const wrapper = mount(ReportModeControls, {
      props: { modelValue: 'strict' },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('Nur belegte Claims')
  })

  it('rendert is-disabled-Klasse wenn disabled=true', () => {
    const wrapper = mount(ReportModeControls, {
      props: { modelValue: 'balanced', disabled: true },
      global: globalConfig,
    })
    expect(wrapper.find('.mode-row').classes()).toContain('is-disabled')
  })
})
